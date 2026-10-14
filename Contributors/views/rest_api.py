import json

from PIL.ImageChops import offset
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
    ContributorHistory.objects.create(
        contributor=contributor,
        event_category=event_category,
        event_type=event_type,
        details = details,
        user=user,
    )

def _read_json_payload(request):
    try:
        return json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return None

def _apply_contributor_payload(contributor, payload):
    allowed_fields = {
        "contributor_type",
        "contributor_name",
        "contact_name",
        "phone",
        "email",
        "description",
    }

    for field in allowed_fields:
        if field in payload:
            setattr(contributor, field, payload[field])

    return contributor


# TODO - move this to the model (separate data vs access).
def _validate_contributor(contributor):
    errors = {}

    if not contributor.contributor_type.strip():
        errors["contributor_type"] = "Contributor type is required."

    if not contributor.contributor_name.strip():
        errors["contributor_name"] = "Company name is required."

    if contributor.phone and len(contributor.phone) > 12:
        errors["phone"] = "Phone must be 12 characters or fewer."

    if contributor.email:
        try:
            validate_email(contributor.email)
        except ValidationError:
            errors["email"] = "Enter a valid email address."

    if contributor.description and len(contributor.description) > 1000:
        errors["description"] = "Description must be 1000 characters or fewer."

    if contributor.contact_name and len(contributor.contact_name) > 120:
        errors["contact_name"] = "Contact name must be 120 characters or fewer."

    # Return model field errors to the spreadsheet rather than raising a server error.
    try:
        contributor.clean_fields()
    except ValidationError as failure:
        for field, messages in failure.message_dict.items():
            errors.setdefault(field, " ".join(messages))

    return errors


def _contributor_response(contributor):
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


@login_required
@require_POST
def contributor_spreadsheet_create(request):
    payload = _read_json_payload(request)

    if payload is None:
        return JsonResponse(
            {
                "ok": False,
                "errors": {
                    "__all__": "Invalid JSON payload.",
                },
            },
            status=400,
        )

    contributor = _apply_contributor_payload(Contributor(), payload)
    errors = _validate_contributor(contributor)

    if errors:
        return JsonResponse(
            {
                "ok": False,
                "errors": errors,
            },
            status=400,
        )

    contributor.full_clean()
    contributor.save()

    print(contributor.id)

    _record_history(contributor, "Data", "New", None, request.user)

    return JsonResponse(
        {
            "ok": True,
            "created": True,
            "contributor": _contributor_response(contributor),
        },
        status=201,
    )


@login_required
@require_POST
def contributor_spreadsheet_save(request, pk):
    contributor = get_object_or_404(Contributor, pk=pk)
    payload = _read_json_payload(request)

    if payload is None:
        return JsonResponse(
            {
                "ok": False,
                "errors": {
                    "__all__": "Invalid JSON payload.",
                },
            },
            status=400,
        )

    # Identify changed fields only after validating that a payload was received.
    changed_fields = {key: (value, getattr(contributor, key)) for key, value in payload.items()
                      if value != getattr(contributor, key)}

    contributor = _apply_contributor_payload(contributor, payload)
    errors = _validate_contributor(contributor)

    if errors:
        return JsonResponse(
            {
                "ok": False,
                "errors": errors,
            },
            status=400,
        )

    contributor.full_clean()
    contributor.save(
        update_fields=[
            "contributor_type",
            "contributor_name",
            "contact_name",
            "phone",
            "email",
            "description",
        ]
    )

    _record_history(contributor, "Data", "Changed",
                    details='\n'.join([f"changed {field} to `{old}` from `{new}`"
                            for field, (old, new) in changed_fields.items()]),
                    user = request.user)
    return JsonResponse(
        {
            "ok": True,
            "created": False,
            "contributor": _contributor_response(contributor),
        }
    )

# TODO - need a suspend endpoint
