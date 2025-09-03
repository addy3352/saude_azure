import os, json
from flask import Flask, request, jsonify ,render_template
import httpx
from utils.auth import functions_auth_headers
from utils.storage import save_message, save_decision
from utils.functions_client import start_sre_triage, agent_info_request

  
AGENT_SRE_FUNC_URL   = os.getenv("AGENT_SRE_FUNC_URL")
AGENT_INFO_FUNC_URL  = os.getenv("AGENT_INFO_FUNC_URL")
AGENT_SRE_DURABLE_BASE = os.getenv("AGENT_SRE_DURABLE_BASE")  # .../runtime/webhooks/durabletask/instances
 
app = Flask(__name__)

# ensure Jinja sees file mtime changes in production
#app.config["TEMPLATES_AUTO_RELOAD"] = True
#app.jinja_env.auto_reload = True

@app.route("/")
def dashboard():
    # Data is fetched client-side from:
    #   /api/resources/summary
    #   /api/sre/last-decisions
    print("I am here ")
    return render_template("dashboard.html")
  
@app.get("/health")
def health():
    return {"ok": True, "service": "saude-app"}

# ------------------ Agent façade routes (pretty paths) ------------------
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

# ------------------ Durable status proxy for dashboard ------------------
@app.get("/status/<instance_id>")
def get_status(instance_id: str):
    # Forward to Durable status endpoint: GET /instances/{id}?showHistory=true
    url = f"{AGENT_SRE_DURABLE_BASE}/{instance_id}"
    params = {"showHistory": "true"}
    with httpx.Client(timeout=20) as c:
        r = c.get(url, params=params, headers=functions_auth_headers("sre"))
        return (r.text, r.status_code, {"Content-Type": r.headers.get("Content-Type", "application/json")})

# ------------------ Minimal chat stub (optional) ------------------
# This shows how your AOAI tool-calls would hit the pretty routes above.
# Replace with your real chat orchestration.
@app.post("/chat")
def chat_stub():
    body = request.get_json(force=True)
    conversation_id = body.get("conversation_id", "default-conv")
    user_msg = body.get("message", "")

    # Save user message
    save_message(conversation_id, "user", user_msg)

    # DEMO: If the user mentions "triage", simulate calling SRE
    if "triage" in user_msg.lower():
        # You would normally parse args out of the message or from ADF alert payload
        payload = {
            "subscription_id": "<subid>",
            "resource_group": "<rg>",
            "factory_name": "<adf>",
            "run_id": "<runid>",
            "pipeline_name": "<pipeline>",
            "expected_path": None
        }
#        with httpx.Client(timeout=60) as c:
#            r = c.post("/agent-sre/api/triage", json=payload)
#            data = r.json()
# AFTER (good: calls Function App URL with headers)
        data = start_sre_triage(payload)
        save_message(conversation_id, "assistant", f"Triage started: {data}")
        return jsonify({"reply": f"Triage started: {data}"})

    # DEMO: inventory
    if "list vms" in user_msg.lower():
        payload = {"op": "list_vms", "filter": "tags.env =~ 'prod'"}
#        with httpx.Client(timeout=60) as c:
#            r = c.post("/agent-info/api/route", json=payload)
#            data = r.json()
        data = start_sre_triage(payload)
        save_message(conversation_id, "assistant", json.dumps(data)[:1000])
        return jsonify({"reply": data})

    # Default echo
    save_message(conversation_id, "assistant", "How can I help? (try 'triage' or 'list vms')")
    return jsonify({"reply": "How can I help? (try 'triage' or 'list vms')"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))