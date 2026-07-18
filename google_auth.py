"""Google credentials for Drive uploads.

Prefers a service account (headless / daily pipeline). Falls back to
Desktop user OAuth + token.pickle (Streamlit / interactive login).
"""

from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.exceptions import RefreshError
import pickle
import os

SCOPES = ["https://www.googleapis.com/auth/drive"]
SERVICE_ACCOUNT_FILE = "service_account.json"
TOKEN_PICKLE = "token.pickle"
OAUTH_CLIENT_FILE = "oauth_client.json"


def get_service_account_credentials():
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        return None
    return service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=SCOPES,
    )


def get_user_credentials():
    """Desktop OAuth — opens a browser when token.pickle is missing/invalid."""
    creds = None

    if os.path.exists(TOKEN_PICKLE):
        with open(TOKEN_PICKLE, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError as e:
                raise RefreshError(
                    "token.pickle refresh failed (invalid_grant). "
                    f"Delete {TOKEN_PICKLE} and re-login, or use {SERVICE_ACCOUNT_FILE} "
                    "for the daily pipeline."
                ) from e
        else:
            if not os.path.exists(OAUTH_CLIENT_FILE):
                raise FileNotFoundError(
                    f"Need {SERVICE_ACCOUNT_FILE} or {OAUTH_CLIENT_FILE} for Google auth"
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                OAUTH_CLIENT_FILE,
                SCOPES,
            )
            creds = flow.run_local_server(
                port=0,
                access_type="offline",
                prompt="consent",
            )

        with open(TOKEN_PICKLE, "wb") as f:
            pickle.dump(creds, f)

    return creds


def get_credentials():
    """Service account if present; otherwise user OAuth."""
    sa = get_service_account_credentials()
    if sa is not None:
        return sa
    return get_user_credentials()
