import os
import json
import datetime as dt
from pathlib import Path
import string
import httpx
from flask import Flask, request, jsonify, render_template
from openai import AzureOpenAI
from utils.auth import functions_auth_headers
from utils.storage import save_message, save_decision
from utils.functions_client import start_sre_triage, agent_info_request
from utils.storage import list_decisions,list_api_logs  # snippet below
from azure.identity import DefaultAzureCredential
from azure.core.exceptions import AzureError
from azure.mgmt.resourcegraph import ResourceGraphClient
from azure.mgmt.resourcegraph.models import QueryRequest
from azure.storage.blob import BlobClient
from azure.data.tables import TableServiceClient
from collections import defaultdict

# ----- env / config ----------------------------------------------------------
# load_dotenv()  # no-op in App Service but useful locally

AGENT_SRE_FUNC_URL      = os.getenv("AGENT_SRE_FUNC_URL")
AGENT_INFO_FUNC_URL     = os.getenv("AGENT_INFO_FUNC_URL")
AGENT_SRE_DURABLE_BASE  = os.getenv("AGENT_SRE_DURABLE_BASE")  # .../runtime/webhooks/durabletask/instances

# Azure OpenAI
AOAI_ENDPOINT    = (os.getenv("AOAI_ENDPOINT") or "").rstrip("/")
AOAI_DEPLOYMENT  = os.getenv("AOAI_DEPLOYMENT", "gpt-4o-mini")
AOAI_API_VERSION = os.getenv("AOAI_API_VERSION", "2024-02-15-preview")
AOAI_API_KEY     = os.getenv("AOAI_API_KEY")  # optional; if absent, code uses MSI/AAD

# Optional: secure webhook signature (Action Group "Enable secure webhook")
#ALERTS_HMAC_SECRET = os.getenv("ALERTS_HMAC_SECRET")  # if set, verify x-ms-signature (not implemented here by default)

# Template dir: prefer mounted dir if it actually has dashboard.html; else use packaged templates
MOUNT_DIR    = os.getenv("TEMPLATE_DIR", "/mnt/templates")
DEFAULT_DIR = str(Path(__file__).parent / "templates")
TEMPLATE_CANDIDATE = MOUNT_DIR if Path(MOUNT_DIR, "dashboard.html").exists() else DEFAULT_DIR

app = Flask(__name__)
# app.config["TEMPLATES_AUTO_RELOAD"] = True
# app.jinja_env.auto_reload = True

# ----- small asserts to catch misconfig at startup ---------------------------
if not (AGENT_SRE_FUNC_URL and AGENT_SRE_FUNC_URL.startswith("http")):
    print("[WARN] AGENT_SRE_FUNC_URL not set or invalid; /agent-sre proxies will fail.")
if not (AGENT_INFO_FUNC_URL and AGENT_INFO_FUNC_URL.startswith("http")):
    print("[WARN] AGENT_INFO_FUNC_URL not set or invalid; /agent-info proxies will fail.")

# ============================================================================ #
#        Azure Monitor -> Webhook                                              #
# ============================================================================ #

def _parse_resource_id(rid: str) -> dict:
    """Extract subscription, RG, factory from a resourceId."""
    try:
        parts = rid.strip("/").split("/")
        low = [p.lower() for p in parts]
        def get(seg):
            return parts[low.index(seg)+1] if seg in low else None
        return {
            "subscription_id": get("subscriptions"),
            "resource_group":  get("resourcegroups"),
            "factory_name":    get("factories"),
        }
    except Exception:
        return {"subscription_id": None, "resource_group": None, "factory_name": None}

def _from_metric_alert(payload: dict) -> dict | None:
    """Metric alert: e.g., PipelineFailedRuns > 0."""
    ctx = payload.get("data", {}).get("alertContext", {})
    conds = ctx.get("condition", {}).get("allOf", [])
    pipeline = None
    metric   = None
    for c in conds:
        metric = metric or c.get("metricName")
        for d in c.get("dimensions", []):
            if d.get("name", "").lower() in ("pipelinename", "pipeline", "pipeline name"):
                pipeline = d.get("value")
    essentials = payload.get("data", {}).get("essentials", {})
    targets = essentials.get("alertTargetIDs") or []
    ids = _parse_resource_id(targets[0]) if targets else {}
    if not pipeline and not ids:
        return None
    return {
        **ids,
        "pipeline_name": pipeline,
        "run_id": None,      # metric alerts don't include it
        "metric": metric,
        "alert_rule": essentials.get("alertRule"),
        "severity": essentials.get("severity"),
    }

def _from_kql_alert(payload: dict) -> dict | None:
    """Scheduled query (Log Analytics) alert, often includes RunId, PipelineName."""
    ctx = payload.get("data", {}).get("alertContext", {})
    rows = ctx.get("SearchQueryResults")
    if isinstance(rows, list) and rows:
        r = rows[0]
        return {
            "subscription_id": r.get("SubscriptionId"),
            "resource_group":  r.get("ResourceGroupName"),
            "factory_name":    r.get("DataFactoryName") or r.get("FactoryName"),
            "pipeline_name":   r.get("PipelineName"),
            "run_id":          r.get("RunId"),
        }
    tables = ctx.get("tables")
    if isinstance(tables, list) and tables:
        cols = [c["name"] for c in tables[0].get("columns", [])]
        if tables[0].get("rows"):
            row = tables[0]["rows"][0]
            rec = dict(zip(cols, row))
            return {
                "subscription_id": rec.get("SubscriptionId"),
                "resource_group":  rec.get("ResourceGroupName"),
                "factory_name":    rec.get("DataFactoryName") or rec.get("FactoryName"),
                "pipeline_name":   rec.get("PipelineName"),
                "run_id":          rec.get("RunId"),
            }
    return None

def _heuristic(triage_ctx: dict, alert: dict) -> dict:
    """Fallback classifier when AOAI is unavailable."""
    blob = json.dumps(alert).lower()
    if any(x in blob for x in ["blobnotfound", "specified blob does not exist", "no such file", "404", "path not found"]):
        return {"category": "FileNotFound", "retryable": True,  "expected_path": None, "why": "Blob/file missing"}
    if any(x in blob for x in ["authorizationpermissionmismatch", "authorizationfailure", "authentication failed", "403"]):
        return {"category": "Auth",           "retryable": False, "expected_path": None, "why": "Permission/auth issue"}
    if any(x in blob for x in ["503", "service unavailable", "throttle", "throttl", "timeout", "econnreset", "etimedout"]):
        return {"category": "Transient",    "retryable": True,  "expected_path": None, "why": "Transient/network"}
    return {"category": "Other",             "retryable": False, "expected_path": None, "why": "Default fallback"}

def _aoai_headers() -> dict:
    if AOAI_API_KEY:
        return {"api-key": AOAI_API_KEY, "Content-Type": "application/json"}
    # Managed Identity / AAD
    try:
        from azure.identity import DefaultAzureCredential
        token = DefaultAzureCredential().get_token("https://cognitiveservices.azure.com/.default").token
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    except Exception:
        return {"Content-Type": "application/json"}  # will 401; caller falls back to heuristic

def _classify_with_aoai(alert: dict, triage_ctx: dict) -> dict:
    """Call Azure OpenAI to classify failure intent. Returns {category, retryable, expected_path, why}."""
    if not AOAI_ENDPOINT or not AOAI_DEPLOYMENT:
        return _heuristic(triage_ctx, alert)

    url = f"{AOAI_ENDPOINT}/openai/deployments/{AOAI_DEPLOYMENT}/chat/completions?api-version={AOAI_API_VERSION}"
    system = (
        "You are an expert SRE classifier for Azure Data Factory failures. "
        "Your task is to analyze the provided JSON alert and classify the failure. "
        "You MUST respond with a STRICT JSON object containing the following keys: "
        "'category' (string), 'retryable' (boolean), 'expected_path' (string or null), and 'why' (string). "
        "Choose the 'category' from these options: 'FileNotFound', 'Transient', 'Auth', or 'Other'. "
        "The 'expected_path' should only be set if you can clearly infer a missing file path from the alert message. "
        "The 'why' field should be a concise, one-sentence explanation for your classification. "
        "\n\nExample Output:\n"
        "```json\n"
        "{\n"
        "  \"category\": \"FileNotFound\",\n"
        "  \"retryable\": true,\n"
        "  \"expected_path\": \"/data/source/my-missing-file.csv\",\n"
        "  \"why\": \"The alert indicates a 404 error, specifying a missing blob.\"\n"
        "}\n"
        "```\n"
        "\n\nCategory Definitions:\n"
        "- 'FileNotFound': The error clearly indicates a missing blob, path, or file (e.g., 404 error). "
        "- 'Transient': The error is temporary and related to network issues, throttling, or service unavailability (e.g., 503 error, connection reset). "
        "- 'Auth': The error is due to an authentication or authorization failure (e.g., 401, 403, AADSTS error). "
        "- 'Other': The error does not fit into any of the above categories. "
    )
    payload = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",    "content": json.dumps({"alert": alert, "context": triage_ctx}, ensure_ascii=False)},
        ],
        "temperature": 0.0,
        "max_tokens": 300,
        "response_format": {"type": "json_object"}
    }
    try:
        with httpx.Client(timeout=20) as c:
            r = c.post(url, headers=_aoai_headers(), json=payload)
            r.raise_for_status()
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            return json.loads(content)
    except Exception as ex:
        print(f"[AOAI] classify error: {ex}")
        return _heuristic(triage_ctx, alert)

@app.post("/alerts/adf")
def handle_adf_alert():
    """Action Group webhook target. Parses Common Alert Schema, classifies with AOAI, then
        either calls Agent-SRE (retryable/FileNotFound) or accepts for notification."""
    print("I am alerted before")
    alert = request.get_json(force=True, silent=True) or {}
    print("I am alerted after {}".format(alert))

    schema_id = str(alert.get("schemaId", ""))

    # 1) Parse alert to triage context
    triage_ctx = None
    if schema_id.startswith("AzureMonitorMetric"):
        triage_ctx = _from_metric_alert(alert)
    elif schema_id.startswith("AzureMonitor"):
        triage_ctx = _from_kql_alert(alert) or _from_metric_alert(alert)
    else:
        # accept compact client payloads too
        if "pipeline_name" in alert or "pipelineName" in alert:
            triage_ctx = {
                "subscription_id": alert.get("subscription_id"),
                "resource_group":  alert.get("resource_group"),
                "factory_name":    alert.get("factory_name"),
                "pipeline_name":   alert.get("pipeline_name") or alert.get("pipelineName"),
                "run_id":          alert.get("run_id") or alert.get("runId"),
            }

    if not triage_ctx:
        # Return 202 so Azure Monitor doesn't keep retrying
        return jsonify({"status": "accepted", "note": "Unrecognized alert shape"}), 202

    # 2) AOAI classification (with heuristic fallback)
    classification = _classify_with_aoai(alert, triage_ctx)

    # 3) Persist decision (don't let storage issues break the webhook)
    try:
        save_decision(
            conversation_id=triage_ctx.get("run_id", "unknown"),
            agent="sre",
            category=classification.get("category"),
            action="classified",
            attempt=0,
            context_json=json.dumps({"alert": alert, "context": triage_ctx}),
            ttl_days=30
        )
    except Exception as ex:
        print(f"[WARN] save_decision failed: {ex}")

    # 4) Route to Agent-SRE if retryable or FileNotFound; else accept (notification-only)
    go_to_sre = bool(classification.get("retryable")) or classification.get("category") == "FileNotFound"

    if go_to_sre:
        triage_event = {
            "source": "azure-monitor",
            "receivedAt": dt.datetime.utcnow().isoformat() + "Z",
            "context": {
                **triage_ctx,
                "expected_path": classification.get("expected_path"),
                "category": classification.get("category"),
                "why": classification.get("why"),
            },
            "raw": alert,
        }
        try:
            result = start_sre_triage(triage_event)  # your helper posts to AGENT_SRE_FUNC_URL
            return jsonify({"status": "queued", "route": "agent-sre", "result": result, "classification": classification}), 202
        except Exception as ex:
            # still 202 so the Alert pipeline doesn't hammer retries
            return jsonify({"status": "accepted", "route": "agent-sre", "forwardError": str(ex), "classification": classification}), 202
    else:
        # Non-retryable -> notification path (Teams/email via Action Group/Logic App handled elsewhere)
        return jsonify({"status": "accepted", "route": "notify", "classification": classification}), 202

# ============================================================================ #
#         Proxy / Utility APIs                                                 #
# ============================================================================ #
# ============================================================================ #
#         For Dashboard Utility APIs                                                 #
# ============================================================================ #

# Azure Resource Graph helpers
def get_arg_counts(limit: int = 20) -> list[dict]:
    _cred = DefaultAzureCredential(exclude_interactive_browser_credential=False)
    SUB = os.getenv("SUBSCRIPTION_ID")
    KQL = """
    resources
    | summarize count() by type
    | project product = tostring(split(type, "/", 1)[1]), count
    | order by count desc
    """
    try:
        cl = ResourceGraphClient(credential=_cred)
        req = QueryRequest(subscriptions=[SUB], query=KQL)
        res = cl.resources(req)
        rows = res.data or []
        items = [{"product": r[0], "count": int(r[1])} for r in rows]
        return items[:limit]
    except Exception as ex:
        print(f"[ARG] Query error: {ex}")
        return []

# Terraform state helpers
def _read_tfstate() -> dict | None:
    ACC = os.getenv("TF_STATE_ACCOUNT")
    CON = os.getenv("TF_STATE_CONTAINER")
    BLOB = os.getenv("TF_STATE_BLOB")
    try:
        if not (ACC and CON and BLOB):
            return None
        _cred = DefaultAzureCredential(exclude_interactive_browser_credential=False)
        bc = BlobClient(account_url=f"https://{ACC}.blob.core.windows.net", container_name=CON, blob_name=BLOB, credential=_cred)
        if not bc.exists():
            return None
        data = bc.download_blob(max_concurrency=1).readall()
        return json.loads(data)
    except Exception as ex:
        print(f"[TFSTATE] Read error: {ex}")
        return None

def get_tf_counts() -> dict[str, int]:
    state = _read_tfstate() or {}
    counts: dict[str, int] = defaultdict(int)
    for res in (state.get("resources") or []):
        t = str(res.get("type", ""))
        if not t.startswith("azurerm_"):
            continue
        mapping = {
            "azurerm_storage_account": "storageaccounts",
            "azurerm_linux_web_app": "sites",
            "azurerm_windows_web_app": "sites",
            "azurerm_service_plan": "serverfarms",
            "azurerm_monitor_action_group": "actiongroups",
            "azurerm_log_analytics_workspace": "workspaces",
            "azurerm_network_watcher": "networkwatchers",
            "azurerm_linux_function_app": "sites",
            "azurerm_windows_function_app": "sites",
        }
        product = mapping.get(t)
        if not product:
            product = t.replace("azurerm_", "").replace("_", "") + "s"
        instances = res.get("instances") or []
        counts[product] += len(instances) if instances else 1
    return dict(counts)

def top_products_with_overlay(limit: int = 12) -> list[dict]:
    arg = get_arg_counts(limit=100)
    tf = get_tf_counts()
    out = []
    for item in arg:
        p = item["product"]
        out.append({
            "product": p,
            "azure_total": item["count"],
            "created_by_terraform": tf.get(p, 0)
        })
    for p, c in tf.items():
        if p not in {i["product"] for i in arg}:
            out.append({"product": p, "azure_total": 0, "created_by_terraform": c})
    out.sort(key=lambda x: x["azure_total"], reverse=True)
    return out[:limit]

# Azure Table Storage helpers
def last_decisions(limit: int = 20) -> list[dict]:
    ACCOUNT_URL = os.getenv("STORAGE_ACCOUNT_URL")
    TABLE_DECISIONS = os.getenv("TABLE_DECISIONS", "AgentDecisions")
    try:
        _cred = DefaultAzureCredential(exclude_interactive_browser_credential=False)
        _svc = TableServiceClient(endpoint=ACCOUNT_URL, credential=_cred)
        _dec = _svc.get_table_client(TABLE_DECISIONS)
        rows = list(_dec.list_entities(results_per_page=limit * 5))
        rows.sort(key=lambda e: e.get("createdAt", ""), reverse=True)
        out = []
        for e in rows[:limit]:
            out.append({
                "createdAt": e.get("createdAt"),
                "pipeline": e.get("PartitionKey"),
                "run_id": e.get("RowKey"),
                "agent": "sre",
                "category": e.get("category"),
                "action": e.get("action"),
                "attempt": 0,
                "context": e.get("payload") or e.get("contextJson"),
            })
        return out
    except Exception as ex:
        print(f"[TABLES] Query error: {ex}")
        return []

@app.get("/api/resources/summary")
def api_resources_summary():
    limit = int(request.args.get("limit", 10))
    data = top_products_with_overlay(limit=limit)
    return jsonify({"items": data})

@app.get("/api/sre/last-decisions")
def api_sre_last_decisions():
    limit = int(request.args.get("limit", 20))
    items = last_decisions(limit=limit)
    return jsonify({"items": items})

@app.get("/api/sre/actions")
def api_sre_actions():
    pipeline = request.args.get("pipeline")
    top = int(request.args.get("top", 50))
    items = list_decisions(pipeline=pipeline, top=top)
    return jsonify(items), 200

@app.route("/")
def dashboard():
    # data fetched client-side via your API routes
    return render_template("dashboard.html")

@app.get("/healthz")
def healthz():
    return {"ok": True, "template_dir": TEMPLATE_CANDIDATE}, 200

@app.get("/health")
def health():
    return {"ok": True, "service": "saude-app"}, 200

# Pretty façade -> Functions (absolute URLs required)
@app.post("/agent-sre/api/triage")
def proxy_sre():
    payload = request.get_json(force=True)
    with httpx.Client(timeout=60) as c:
        r = c.post(AGENT_SRE_FUNC_URL, json=payload, headers=functions_auth_headers("sre"))
        return (r.text, r.status_code, {"Content-Type": r.headers.get("Content-Type", "application/json")})

@app.post("/agent-info/api/route")
def proxy_info():
    payload = request.get_json(force=True)
    with httpx.Client(timeout=60) as c:
        r = c.post(AGENT_INFO_FUNC_URL, json=payload, headers=functions_auth_headers("info"))
        return (r.text, r.status_code, {"Content-Type": r.headers.get("Content-Type", "application/json")})

# Durable status (for dashboard)
@app.get("/status/<instance_id>")
def get_status(instance_id: string):
    url = f"{AGENT_SRE_DURABLE_BASE}/{instance_id}"
    params = {"showHistory": "true"}
    with httpx.Client(timeout=20) as c:
        r = c.get(url, params=params, headers=functions_auth_headers("sre"))
        return (r.text, r.status_code, {"Content-Type": r.headers.get("Content-Type", "application/json")})
@app.get("/api/logs/actions")
def api_logs_actions():
    top = int(request.args.get("top", 50))
    items = list_api_logs(top=top)
    return jsonify({"items": items})

# ============================================================================ #
#         Minimal chat stub                                                    #
# ============================================================================ #

@app.post("/chat")
def chat_stub():
    body = request.get_json(force=True)
    conversation_id = body.get("conversation_id", "default-conv")
    user_msg = body.get("message", "")

    save_message(conversation_id, "user", user_msg)

    # DEMO: triage
    if "triage" in user_msg.lower():
        payload = {
            "subscription_id": "<subid>",
            "resource_group": "<rg>",
            "factory_name": "<adf>",
            "run_id": "<runid>",
            "pipeline_name": "<pipeline>",
            "expected_path": None
        }
        data = start_sre_triage(payload)
        save_message(conversation_id, "assistant", f"Triage started: {data}")
        return jsonify({"reply": f"Triage started: {data}"})

    # DEMO: inventory
    if "list vms" in user_msg.lower():
        payload = {"op": "list_vms", "filter": "tags.env =~ 'prod'"}
        data = agent_info_request(payload)  # fixed: call Agent-Info helper
        save_message(conversation_id, "assistant", json.dumps(data)[:1000])
        return jsonify({"reply": data})

    save_message(conversation_id, "assistant", "How can I help? (try 'triage' or 'list vms')")
    return jsonify({"reply": "How can I help? (try 'triage' or 'list vms')"})

# ============================================================================ #

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)
