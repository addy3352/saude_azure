import os
import uuid
import datetime as dt
from azure.identity import DefaultAzureCredential
from azure.data.tables import TableServiceClient

ACCOUNT_URL = os.getenv("STORAGE_ACCOUNT_URL")
TABLE_MESSAGES = os.getenv("TABLE_MESSAGES", "Messages")
TABLE_DECISIONS = os.getenv("TABLE_DECISIONS", "AgentDecisions")

_cred = DefaultAzureCredential(exclude_interactive_browser_credential=False)
_svc = TableServiceClient(endpoint=ACCOUNT_URL, credential=_cred)
_messages = _svc.get_table_client(TABLE_MESSAGES)
_decisions = _svc.get_table_client(TABLE_DECISIONS)

# Ensure tables exist (no-op if already there)
try:
    _messages.create_table()
except Exception:
    pass
try:
    _decisions.create_table()
except Exception:
    pass

def save_message(conversation_id: str, role: str, content: str, tool_calls: str | None = None, ttl_days: int = 30):
    entity = {
        "PartitionKey": conversation_id,
        "RowKey": str(uuid.uuid4()),
        "role": role,
        "content": content,
        "toolCallsJson": tool_calls or "",
        "createdAt": dt.datetime.utcnow().isoformat(),
        "ttl": ttl_days * 86400,
    }
    _messages.upsert_entity(entity)


def save_decision(conversation_id: str, agent: str, category: str, action: str, attempt: int, context_json: str, ttl_days: int = 30):
    entity = {
        "PartitionKey": conversation_id,
        "RowKey": str(uuid.uuid4()),
        "agent": agent,
        "category": category,
        "action": action,
        "attempt": attempt,
        "contextJson": context_json,
        "createdAt": dt.datetime.utcnow().isoformat(),
        "ttl": ttl_days * 86400,
    }
    _decisions.upsert_entity(entity)