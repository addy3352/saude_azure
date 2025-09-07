import os
import uuid
import datetime as dt
import json
import logging
from azure.identity import DefaultAzureCredential
from azure.data.tables import TableServiceClient

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ACCOUNT_URL = (os.getenv("STORAGE_ACCOUNT_URL") or "").rstrip("/")
TABLE_MESSAGES = os.getenv("TABLE_MESSAGES", "Messages")
TABLE_DECISIONS = os.getenv("TABLE_DECISIONS", "AgentDecisions")
TABLE_API_LOGS = os.getenv("TABLE_API_LOGS", "ApiLogs")


_cred = DefaultAzureCredential()

# create service client (use endpoint, not account_url)
if not ACCOUNT_URL:
    raise RuntimeError("STORAGE_ACCOUNT_URL app setting is missing")
_svc = TableServiceClient(endpoint=ACCOUNT_URL, credential=_cred)

def _table(name: str):
    """
    Lazily create a table and return its client.
    """
    try:
        _svc.create_table_if_not_exists(name)
        return _svc.get_table_client(name)
    except Exception as e:
        logger.error(f"Error initializing table client for '{name}': {e}")
        raise  # Re-raise to ensure app fails if tables can't be set up
import json, uuid, datetime as dt
from typing import Optional, Dict, Any, List
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential, ChainedTokenCredential
from azure.data.tables import TableServiceClient

# ...existing constants/credential...

MAX_STR = 32000  # stay well under Table Storage per-property limits

def _svc() -> TableServiceClient:
    return TableServiceClient(endpoint=ACCOUNT_URL, credential=_cred)

def _now_iso() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def save_decision(
    *,
    agent: str,
    category: str,
    action: str,
    attempt: int,
    pipeline_name: Optional[str] = None,
    status: Optional[str] = None,
    why: Optional[str] = None,
    run_id: Optional[str] = None,
    instance_id: Optional[str] = None,
    context_json: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,      # <-- NEW (dict)
    payload_json: Optional[str] = None,            # <-- NEW (string)
    ttl_days: int = 30,
    **_ignored,  # tolerate extra kwargs like conversation_id
):
    # normalize payload
    if payload_json is None and payload is not None:
        try:
            payload_json = json.dumps(payload, default=str)
        except Exception:
            payload_json = str(payload)

    svc = _svc()
    svc.create_table_if_not_exists(TABLE_DECISIONS)
    t = svc.get_table_client(TABLE_DECISIONS)

    row = {
        "PartitionKey": (pipeline_name or "unknown"),
        "RowKey": uuid.uuid4().hex,
        "createdAt": _now_iso(),
        "agent": agent,
        "category": category,
        "action": action,
        "attempt": int(attempt or 0),
        "status": status or "",
        "why": (why or "")[:4096],
        "pipeline": pipeline_name or "",
        "run_id": run_id or "",
        "instance_id": instance_id or "",
        "context": (context_json or "")[:MAX_STR],
        "payload": (payload_json or "")[:MAX_STR],  # <-- NEW column
        "ttlDays": int(ttl_days),
    }
    t.upsert_entity(row)

def list_decisions(pipeline: Optional[str] = None, top: int = 50) -> List[Dict[str, Any]]:
    from itertools import islice
    svc = _svc()
    svc.create_table_if_not_exists(TABLE_DECISIONS)
    t = svc.get_table_client(TABLE_DECISIONS)

    it = t.query_entities(f"PartitionKey eq '{pipeline}'") if pipeline else t.list_entities()
    rows = list(islice(it, top * 3))
    rows.sort(key=lambda e: e.get("createdAt", ""), reverse=True)

    out = []
    for e in rows[:top]:
        out.append({
            "createdAt": e.get("createdAt"),
            "pipeline": e.get("pipeline") or e.get("PartitionKey"),
            "category": e.get("category"),
            "action": e.get("action"),
            "status": e.get("status"),
            "why": e.get("why"),
            "run_id": e.get("run_id"),
            "instance_id": e.get("instance_id"),
            "context": e.get("context") or "",
            "payload": e.get("payload") or "",  # <-- expose payload too
        })
    return out




def save_message(conversation_id: str, role: str, text: str):
    t = _table(TABLE_MESSAGES)
    pk = conversation_id or "default"
    rk = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ")
    t.upsert_entity({"PartitionKey": pk, "RowKey": rk, "role": role, "text": text})
    logger.info(f"Saved message to table '{TABLE_MESSAGES}' for conversation '{pk}'.")




def save_api_log(endpoint: str, method: str, status_code: int, duration_ms: float, payload: dict, response: dict):
    t = _table(TABLE_API_LOGS)
    pk = endpoint or "unknown"
    rk = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ")
    entity = {
        "PartitionKey": pk,
        "RowKey": rk,
        "method": method,
        "statusCode": status_code,
        "durationMs": duration_ms,
        "payloadJson": json.dumps(payload),
        "responseJson": json.dumps(response),
    }
    t.upsert_entity(entity)
    logger.info(f"Saved API log to table '{TABLE_API_LOGS}' for endpoint '{pk}'.")



def list_api_logs(top: int = 50):
    t = _table(TABLE_API_LOGS)
    pager = t.list_entities(results_per_page=top)
    items = []
    try:
        for page in pager.by_page():
            for ent in page:
                items.append({
                    "createdAt": ent.get("createdAt") or str(ent.get("Timestamp")),
                    "endpoint": ent.get("PartitionKey"),
                    "method": ent.get("method"),
                    "statusCode": ent.get("statusCode"),
                    "durationMs": ent.get("durationMs"),
                    "payload": ent.get("payloadJson"),
                    "response": ent.get("responseJson"),
                })
            break
    except Exception as ex:
        logger.error(f"[TABLES] Query error: {ex}")
    
    items.sort(key=lambda x: x.get("createdAt",""), reverse=True)
    return items[:top]
