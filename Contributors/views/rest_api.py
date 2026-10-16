import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_POST

from Contributors.models import Contributor, ContributorHistory


# TODO Add support for 'details view' - ie socials, company icons etc

# Make this class based with support for flexible actions
# Specific permissions etc

def _record_history(contributor, event_category:str, event_type:str, details:str|None = None, user=None):
    """Keep inline edits attributable to the acting user."""
    ContributorHistory.objects.create(
        contributor=contributor,
        event_category=event_category,
        event_type=event_type,
        details = details,
        user=user,
    )

def _read_json_payload(request):
    """Decode the editor request, distinguishing invalid JSON from form errors."""
    # Malformed request bodies need a field-level response rather than a server error.
    try:
        return json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return None

def _apply_contributor_payload(contributor, payload):
    """Restrict inline edits to the supported contributor fields."""
    allowed_fields = {
        "contributor_type",
        "contributor_name",
        "contact_name",
        "phone",
        "email",
        "description",
    }

    # The inline editor must never assign arbitrary model attributes.
    for field in allowed_fields:
        # Omitted fields retain their existing value during partial row edits.
        if field in payload:
            setattr(contributor, field, payload[field])

    return contributor


# TODO - move this to the model (separate data vs access).
def _validate_contributor(contributor):
    """Combine friendly inline validation with model field constraints."""
    errors = {}

    # A contributor type is required for the specialised lists to find this row.
    if not contributor.contributor_type.strip():
        errors["contributor_type"] = "Contributor type is required."

    # Whitespace-only names cannot identify contributors in the spreadsheet.
    if not contributor.contributor_name.strip():
        errors["contributor_name"] = "Company name is required."

    # Keep inline validation consistent with the supported phone input length.
    if contributor.phone and len(contributor.phone) > 12:
        errors["phone"] = "Phone must be 12 characters or fewer."

    # An absent address is allowed; a supplied one must be deliverable in principle.
    if contributor.email:
        # Use Django email validation so browser and server address rules stay aligned.
        try:
            validate_email(contributor.email)
        except ValidationError:
            errors["email"] = "Enter a valid email address."

    # Reject oversized descriptions before database field validation obscures the cause.
    if contributor.description and len(contributor.description) > 1000:
        errors["description"] = "Description must be 1000 characters or fewer."

    # Return the same contact-name limit used by the browser editor.
    if contributor.contact_name and len(contributor.contact_name) > 120:
        errors["contact_name"] = "Contact name must be 120 characters or fewer."

    _merge_model_errors(contributor, errors)
    return errors


def _merge_model_errors(contributor, errors):
    """Preserve friendly spreadsheet errors while adding model-level restrictions."""
    # Model validation catches field constraints beyond the inline editor's rules.
    try:
        contributor.clean_fields()
    except ValidationError as failure:
        # Friendly editor messages take priority when both validators reject a field.
        for field, messages in failure.message_dict.items():
            errors.setdefault(field, " ".join(messages))


def _contributor_response(contributor):
    """Return row data and the endpoint URLs needed by newly created rows."""
    return {
        "id": contributor.pk,
        "contributor_type": contributor.contributor_type,
        "contributor_name": contributor.contributor_name,
        "contact_name": contributor.contact_name,
        "phone": contributor.phone,
        "email": contributor.email,
        "description": contributor.description,
        "save_url": reverse("contributors:spreadsheet_save", args=[contributor.pk]),
        "contact_history_url": reverse("contributors:contact_history", args=[contributor.pk]),
        "details_url": reverse("contributors:details", args=[contributor.pk]),
    }


def _invalid_payload_response():
    """Keep malformed request errors consistent across create and save."""
    return JsonResponse({"ok": False, "errors": {"__all__": "Invalid JSON payload."}}, status=400)


def _save_row_response(contributor, payload, request, *, created):
    """Persist valid fields and the associated audit trail before returning row data."""
    changed_fields = {key: (value, getattr(contributor, key)) for key, value in payload.items()
                      if value != getattr(contributor, key)}
    _apply_contributor_payload(contributor, payload)
    errors = _validate_contributor(contributor)
    # Invalid data remains in the browser for correction rather than being saved partially.
    if errors:
        return JsonResponse({"ok": False, "errors": errors}, status=400)
    contributor.full_clean()
    contributor.save() if created else contributor.save(update_fields=[
        "contributor_type", "contributor_name", "contact_name", "phone", "email", "description",
    ])
    details = None if created else '\n'.join(
        f"changed {field} to `{old}` from `{new}`" for field, (old, new) in changed_fields.items()
    )
    _record_history(contributor, "Data", "New" if created else "Changed", details, request.user)
    return JsonResponse({"ok": True, "created": created, "contributor": _contributor_response(contributor)},
                        status=201 if created else 200)


@login_required
@require_POST
def contributor_spreadsheet_create(request):
    """Create an inline spreadsheet row and its initial history entry."""
    payload = _read_json_payload(request)
    # Invalid JSON cannot be treated as an empty contributor submission.
    if payload is None:
        return _invalid_payload_response()
    return _save_row_response(Contributor(), payload, request, created=True)


@login_required
@require_POST
def contributor_spreadsheet_save(request, pk):
    """Save an existing inline row without changing omitted fields."""
    contributor = get_object_or_404(Contributor, pk=pk)
    payload = _read_json_payload(request)
    # Decode before comparing fields so malformed requests cannot trigger an audit entry.
    if payload is None:
        return _invalid_payload_response()
    return _save_row_response(contributor, payload, request, created=False)
