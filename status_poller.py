import os, json, time
import httpx
from utils.storage import save_message
from utils.auth import functions_auth_headers

AGENT_SRE_DURABLE_BASE = os.getenv("AGENT_SRE_DURABLE_BASE")

# Pull recent instances (you can also maintain a list in Table Storage)
# Durable "instances" query API can be called via POST to .../instances?taskHub=... with filters.
# For MVP, assume you have a list of instance IDs to poll.
INSTANCE_IDS = []  # populate from your alert webhook or Table Storage

while True:
    for inst in INSTANCE_IDS:
        url = f"{AGENT_SRE_DURABLE_BASE}/{inst}"
        with httpx.Client(timeout=20) as c:
            r = c.get(url, params={"showHistory": True}, headers=functions_auth_headers("sre"))
            if r.status_code == 200:
                data = r.json()
                # TODO: compute metrics or aggregate to your UI cache
                save_message("durable-status", "tool", json.dumps({inst: data})[:4000])
    time.sleep(30)