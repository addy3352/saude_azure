import os
from azure.identity import ManagedIdentityCredential, DefaultAzureCredential

USE_AAD = os.getenv("USE_AAD_FOR_FUNCS", "false").lower() == "true"
FUNC_APP_APP_ID_URI = os.getenv("FUNC_APP_APP_ID_URI")

_cred = DefaultAzureCredential(exclude_interactive_browser_credential=False)
_mi_cred = ManagedIdentityCredential()

def functions_auth_headers(kind: str):
    """Return headers to call Function Apps securely.
    If USE_AAD_FOR_FUNCS=true, acquire a bearer token for the Function App.
    Otherwise attach function key header from env/Key Vault.
    """
    if USE_AAD and FUNC_APP_APP_ID_URI:
        token = _cred.get_token(FUNC_APP_APP_ID_URI).token
        return {"Authorization": f"Bearer {token}"}

    key_env = "FUNC_KEY_SRE_SECRET" if kind == "sre" else "FUNC_KEY_INFO_SECRET"
    key = os.getenv(key_env)
    return {"x-functions-key": key} if key else {}