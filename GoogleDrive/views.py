from credentials import google_drive_info
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse
from django.conf import settings

from .forms import UploadToDriveForm

from .models import DriveFile
from .services.google_drive import GoogleDrive
from .services.google_oauth import (
    build_google_oauth_authorize_url,
    exchange_code_for_tokens,
    new_state_value,
    verify_id_token_and_get_claims, get_or_create_company_credential,
)

root_folder_id = google_drive_info.GOOGLE_DRIVE_ROOT_FOLDER_ID  # GarageSale/upload_test

SESSION_STATE_KEY = "google_drive_oauth_state"

#To DO Integrate this into the Team pages - somehow - maybe some sort of basic widget idea ?

@staff_member_required
def drive_connect(request):
    """
    Admin-only: starts OAuth flow to connect the company Google account.
    Uses OAuth 'state' stored in session to protect against OAuth CSRF.
    """
    state = new_state_value()
    request.session[SESSION_STATE_KEY] = state

    redirect_uri = request.build_absolute_uri(reverse("GoogleDrive:drive_oauth_callback"))

    url = build_google_oauth_authorize_url(redirect_uri=redirect_uri, state=state)
    return redirect(url)


@staff_member_required
def drive_oauth_callback(request):
    """
    Admin-only: handles the OAuth callback and stores refresh_token + id_token identity.
    """
    returned_state = request.GET.get("state")
    expected_state = request.session.pop(SESSION_STATE_KEY, None)

    if not expected_state or not returned_state or returned_state != expected_state:
        return HttpResponseBadRequest("Invalid OAuth state. Please try connecting again.")

    error = request.GET.get("error")
    if error:
        return HttpResponseBadRequest(f"Google OAuth error: {error}")

    code = request.GET.get("code")
    if not code:
        return HttpResponseBadRequest("Missing authorization code.")

    redirect_uri = request.build_absolute_uri(reverse("GoogleDrive:drive_oauth_callback"))
    print(redirect_uri)
    token_payload = exchange_code_for_tokens(code=code, redirect_uri=redirect_uri)

    refresh_token = token_payload.get("refresh_token", "")
    raw_id_token = token_payload.get("id_token", "")

    if not refresh_token:
        # Common cause: you already authorized before and Google didn't re-issue a refresh token.
        # Fix: revoke app access in the Google account then reconnect (or adjust consent prompt/scopes).
        return HttpResponseBadRequest("No refresh_token received. Revoke app access and try again.")

    if not raw_id_token:
        return HttpResponseBadRequest("No id_token received. Ensure 'openid email profile' scopes are included.")

    claims = verify_id_token_and_get_claims(raw_id_token=raw_id_token)

    cred = GoogleDrive().credentials
    cred.refresh_token = refresh_token
    cred.google_sub = claims.get("sub", "")
    cred.google_email = claims.get("email", "")
    cred.scopes = "openid email profile https://www.googleapis.com/auth/drive.file"
    cred.root_folder_id = root_folder_id
    cred.save()

    return redirect("GoogleDrive:status")


@staff_member_required
def drive_status(request):
    drive = GoogleDrive()
    return render(request, "GoogleDrive/status.html",
                  {"cred": drive.credentials,
                   "path": drive.get_file_path(drive.credentials.root_folder_id)})


def upload_to_drive(request):
    """
    Regular app users can upload a file; upload uses the single company account credential.
    You should still protect this view with whatever permissions your app requires.
    """
    if not request.user.is_authenticated:
        return HttpResponseForbidden("Login required.")

    cred = GoogleDrive().credentials

    if not cred.is_connected():
        return HttpResponseBadRequest("Google Drive is not connected. Ask an admin to connect it.")

    if request.method == "POST":
        form = UploadToDriveForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded = request.FILES["file"]

            drive = GoogleDrive(cred)
            created = drive.upload_django_uploaded_file(
                uploaded_file=uploaded,
                folder_id=cred.root_folder_id or None,
            )

            DriveFile.objects.create(
                drive_file_id=created["id"],
                name=created.get("name", uploaded.name),
                mime_type=created.get("mimeType", ""),
                size=created.get("size") or None,
                web_view_link=created.get("webViewLink", ""),
                uploaded_by=request.user,
            )

            return redirect("drive_upload_success")

    else:
        form = UploadToDriveForm()

    return render(request, "GoogleDrive/upload.html", {"form": form})


def upload_success(request):
    return render(request, "GoogleDrive/upload_success.html")