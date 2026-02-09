import secrets
import urllib.parse

import requests
from credentials import google_drive_info
from django.conf import settings
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from GoogleDrive.models import GoogleDriveCompanyCredential

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

OAUTH_SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/drive.metadata.readonly"
]


def build_google_oauth_authorize_url(*, redirect_uri: str, state: str) -> str:
    params = {
        "client_id": google_drive_info.GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(OAUTH_SCOPES),
        "access_type": "offline",   # needed for refresh_token
        "prompt": "consent",        # helps ensure refresh_token is returned
        "state": state,
    }
    return GOOGLE_AUTH_URL + "?" + urllib.parse.urlencode(params)


def exchange_code_for_tokens(*, code: str, redirect_uri: str) -> dict:
    resp = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": google_drive_info.GOOGLE_OAUTH_CLIENT_ID,
            "client_secret": google_drive_info.GOOGLE_OAUTH_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def verify_id_token_and_get_claims(*, raw_id_token: str) -> dict:
    """
    Verifies signature and audience, returns claims (includes 'sub', 'email', etc.).
    """
    req = google_requests.Request()
    claims = google_id_token.verify_oauth2_token(
        raw_id_token,
        req,
        google_drive_info.GOOGLE_OAUTH_CLIENT_ID,
    )
    return claims


def new_state_value() -> str:
    return secrets.token_urlsafe(32)


def get_or_create_company_credential() -> GoogleDriveCompanyCredential:
    obj = GoogleDriveCompanyCredential.objects.order_by("-updated_at").first()
    if obj:
        return obj
    return GoogleDriveCompanyCredential.objects.create()
