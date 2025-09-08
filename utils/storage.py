import os
import uuid
import datetime as dt
import json ,uuid
import logging
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential, ChainedTokenCredential
from azure.identity import DefaultAzureCredential
from azure.data.tables import TableServiceClient
from typing import Optional, Dict, Any, List

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ACCOUNT_URL = (os.getenv("STORAGE_ACCOUNT_URL") or "").rstrip("/")
TABLE_MESSAGES = os.getenv("TABLE_MESSAGES", "Messages")
TABLE_DECISIONS = os.getenv("TABLE_DECISIONS", "AgentDecisions")
TABLE_API_LOGS = os.getenv("TABLE_API_LOGS", "ApiLogs")

MAX_STR = 32000  # stay well under Table Storage per-property limits


_cred = ChainedTokenCredential(
    ManagedIdentityCredential(),
    DefaultAzureCredential(exclude_shared_token_cache_credential=True),
)

# create service client (use endpoint, not account_url)
if not ACCOUNT_URL:
    raise RuntimeError("STORAGE_ACCOUNT_URL app setting is missing")


def get_table_service() -> TableServiceClient:
    # Name avoids any clash with previous _svc variable/function
    return TableServiceClient(endpoint=ACCOUNT_URL, credential=_cred)




# ...existing constants/credential...



def _now_iso() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _table(name: str):
    try:
        svc = get_table_service()
        try:
            svc.create_table_if_not_exists(name)
        except ResourceExistsError:
            pass
        return svc.get_table_client(name)
    except Exception as ex:
        logger.error(f"Error initializing table client for '{name}': {ex}")
        raise



def save_decision(
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
    t = get_table(TABLE_DECISIONS)
    entity = {
        "PartitionKey": (pipeline_name or "all"),
        "RowKey": uuid.uuid4().hex,
        "createdAt": _now_iso(),
        "agent": agent,
        "pipeline": pipeline_name or "all",
        "category": category,
        "action": action,
        "attempt": int(attempt),
        "status": status,
        "why": (why or "")[:1024],
        "run_id": run_id,
        "instance_id": instance_id,
        "context": (context_json or "")[:MAX_STR],
        "payload": (payload_json or "")[:MAX_STR],
        "ttlDays": int(ttl_days),
    }
    t.upsert_entity(entity)    
    # normalize payload


def list_decisions(pipeline: Optional[str] = None, top: int = 50) -> List[Dict[str, Any]]:
    t = get_table(TABLE_DECISIONS)
    it = t.query_entities(f"PartitionKey eq '{pipeline}'") if pipeline else t.list_entities()
    rows = list(it)
    rows.sort(key=lambda e: e.get("createdAt", ""), reverse=True)
    return [{
        "createdAt": e.get("createdAt"),
        "pipeline": e.get("pipeline") or e.get("PartitionKey"),
        "category": e.get("category"),
        "action": e.get("action"),
        "status": e.get("status"),
        "why": e.get("why"),
        "run_id": e.get("run_id"),
        "instance_id": e.get("instance_id"),
        "context": e.get("context") or "",
        "payload": e.get("payload") or "",
    } for e in rows[:top]]




def save_message(conversation_id: str, role: str, text: str):
    t = _table(TABLE_MESSAGES)
    pk = conversation_id or "default"
    rk = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ")
    t.upsert_entity({"PartitionKey": pk, "RowKey": rk, "role": role, "text": text})
    logger.info(f"Saved message to table '{TABLE_MESSAGES}' for conversation '{pk}'.")


def save_api_log(endpoint: str, method: str, status_code: int, duration_ms: Optional[int]):
    t = get_table(TABLE_API_LOGS)
    t.upsert_entity({
        "PartitionKey": "apilog",
        "RowKey": uuid.uuid4().hex,
        "createdAt": _now_iso(),
        "endpoint": endpoint[:512],
        "method": method,
        "statusCode": int(status_code),
        "durationMs": int(duration_ms) if duration_ms is not None else None,
    })

def list_api_logs(top: int = 50) -> List[Dict[str, Any]]:
    t = get_table(TABLE_API_LOGS)
    rows = list(t.list_entities())
    rows.sort(key=lambda e: e.get("createdAt", ""), reverse=True)
    return [{
        "createdAt": e.get("createdAt"),
        "endpoint": e.get("endpoint"),
        "method": e.get("method"),
        "statusCode": e.get("statusCode"),
        "durationMs": e.get("durationMs"),
    } for e in rows[:top]]

