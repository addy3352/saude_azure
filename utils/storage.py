import os
import uuid
import datetime as dt
import json ,uuid
import logging
from __future__ import annotations  # makes annotations lazy -> prevents NameError at import time
from typing import Optional, Dict, Any, List  # <-- this fixes "Optional not defined"
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential, ChainedTokenCredential
from azure.identity import DefaultAzureCredential
from azure.data.tables import TableServiceClient

# Set up logging
#logging.basicConfig(level=logging.INFO)
#logger = logging.getLogger(__name__)
log = logging.getLogger("utils.storage")

ACCOUNT_URL = (os.getenv("STORAGE_ACCOUNT_URL") or "").rstrip("/")
TABLE_MESSAGES = os.getenv("TABLE_MESSAGES", "Messages")
TABLE_DECISIONS = os.getenv("TABLE_DECISIONS", "AgentDecisions")
TABLE_API_LOGS = os.getenv("TABLE_API_LOGS", "ApiLogs")



MAX_STR = 32000  # stay well under Table Storage per-property limits


_cred = ChainedTokenCredential(
    ManagedIdentityCredential(),
    DefaultAzureCredential(exclude_shared_token_cache_credential=True),
)


def _service() -> TableServiceClient:
    if not ACCOUNT_URL:
        raise RuntimeError("STORAGE_ACCOUNT_URL is not set")
    # IMPORTANT: in azure-data-tables 12.x use endpoint= not account_url=
    return TableServiceClient(endpoint=ACCOUNT_URL, credential=_cred)





# ...existing constants/credential...



def _now_iso() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def get_table(name: str):
    svc = _service()
    try:
        svc.create_table_if_not_exists(name)
    except ResourceExistsError:
            log.debug(f"create_table_if_not_exists({name}) ignored: {e}")
    return svc.get_table_client(name)


def save_decision(
    conversation_id: str,
    agent: str,
    category: str,
    action: str,
    attempt: int = 0,
    pipeline_name: Optional[str] = None,
    run_id: Optional[str] = None,
    status: Optional[str] = None,
    instance_id: Optional[str] = None,
    context_json: Optional[str] = None,
    why: Optional[str] = None,
) -> None:
    t = get_table(TABLE_DECISIONS)
    entity = {
        "PartitionKey": (pipeline_name or "unknown"),
        "RowKey": f"{(run_id or conversation_id)}-{int(dt.datetime.utcnow().timestamp()*1000)}",
        "createdAt": dt.datetime.utcnow().isoformat() + "Z",
        "conversationId": conversation_id,
        "agent": agent,
        "category": category,
        "action": action,
        "attempt": attempt,
        "pipeline": pipeline_name,
        "run_id": run_id,
        "status": status,
        "instance_id": instance_id,
        "context": context_json,
        "why": why,
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

def list_api_logs(top: int = 50) -> Dict[str, Any]:
    t = get_table(TABLE_API_LOGS)
    items: List[Dict[str, Any]] = []
    for e in t.query_entities("PartitionKey eq 'api'"):
        items.append(e)
        if len(items) >= top:
            break
    return {"items": sorted(items, key=lambda x: x.get("createdAt", ""), reverse=True)}

def add_api_log(endpoint: str, method: str, status_code: int, duration_ms: float) -> None:
    t = get_table(TABLE_API_LOGS)
    now = dt.datetime.utcnow().isoformat() + "Z"
    row_key = f"{int(dt.datetime.utcnow().timestamp()*1000)}"
    t.upsert_entity({
        "PartitionKey": "api",
        "RowKey": row_key,
        "createdAt": now,
        "endpoint": endpoint,
        "method": method,
        "statusCode": status_code,
        "durationMs": duration_ms,
    })

