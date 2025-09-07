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

def save_message(conversation_id: str, role: str, text: str):
    t = _table(TABLE_MESSAGES)
    pk = conversation_id or "default"
    rk = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ")
    t.upsert_entity({"PartitionKey": pk, "RowKey": rk, "role": role, "text": text})
    logger.info(f"Saved message to table '{TABLE_MESSAGES}' for conversation '{pk}'.")

def save_decision(pipeline: str, payload: dict):
    t = _table(TABLE_DECISIONS)
    pk = pipeline or "unknown"
    rk = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ")
    t.upsert_entity({"PartitionKey": pk, "RowKey": rk, **payload})
    logger.info(f"Saved decision to table '{TABLE_DECISIONS}' for pipeline '{pk}'.")

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

def list_decisions(pipeline: str | None, top: int = 50):
    t = _table(TABLE_DECISIONS)
    if pipeline:
        pager = t.query_entities(f"PartitionKey eq '{pipeline}'", results_per_page=top)
    else:
        pager = t.list_entities(results_per_page=top)

    items = []
    try:
        for page in pager.by_page():
            for e in page:
                items.append({
                    "ts": e.get("ts") or str(e.get("Timestamp")),
                    "pipeline_name": e.get("PartitionKey"),
                    "factory": e.get("factory"),
                    "category": e.get("category"),
                    "action": e.get("action"),
                    "status": e.get("status"),
                    "why": e.get("why"),
                    "run_id": e.get("run_id"),
                    "expected_path": e.get("expected_path"),
                    "instance_id": e.get("instance_id"),
                })
            break
    except Exception as ex:
        logger.error(f"[TABLES] Query error: {ex}")
    
    items.sort(key=lambda x: x.get("ts",""), reverse=True)
    return items[:top]

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
