# saude-app/utils/functions_client.py
import os, httpx
from .auth import functions_auth_headers

AGENT_SRE_FUNC_URL  = os.getenv("AGENT_SRE_FUNC_URL")
AGENT_INFO_FUNC_URL = os.getenv("AGENT_INFO_FUNC_URL")

def start_sre_triage(payload: dict) -> dict:
    """Call SRE Durable Function start endpoint with auth headers."""
    with httpx.Client(timeout=60) as c:
        r = c.post(AGENT_SRE_FUNC_URL, json=payload, headers=functions_auth_headers("sre"))
        r.raise_for_status()
        return r.json()

def agent_info_request(payload: dict) -> dict:
    """Call Agent-Info HTTP function with auth headers."""
    with httpx.Client(timeout=60) as c:
        r = c.post(AGENT_INFO_FUNC_URL, json=payload, headers=functions_auth_headers("info"))
        r.raise_for_status()
        return r.json()
