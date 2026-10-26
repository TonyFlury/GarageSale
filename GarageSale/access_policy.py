"""Agreed application capabilities and group bundles; no third-party policy lives here."""
from functools import wraps

from django.conf import settings
from django.core.exceptions import PermissionDenied


# Explicit ownership prevents a newly installed library being swept into cleanup.
PROJECT_APPS = frozenset({"Accounts", "Billboard", "Contributors", "CraftMarket", "DjangoGoogleMap",
                          "GarageSale", "GoogleDrive", "Location", "News", "SaleLocation", "Sponsors", "user_management"})
GROUP_NAMES = ("ExecMember", "Officer", "SponsorshipManager", "PrizeAllocationManager", "CraftMarketManager", "Financier", "WebAdmin", "Volunteer")
CUSTOM_CODES = (
    "access_team_pages", "manage_own_team_profile", "view_all_template_categories", "manage_all_template_categories",
    "view_sponsor_templates", "manage_sponsor_templates", "view_market_templates", "manage_market_templates",
    "contact_sponsor", "email_sponsor", "generate_sponsor_pdf", "import_sponsors", "export_sponsors",
    "add_marketer", "contact_marketer", "invite_marketer", "confirm_marketer", "reject_marketer",
    "email_marketer", "generate_marketer_pdf", "import_marketers", "export_marketers",
    "close_financialyear", "export_location", "access_drive", "view_newsletter", "add_newsletter",
    "change_newsletter", "delete_newsletter", "send_newsletter",
)
CUSTOM_PERMISSIONS = tuple((code, code.replace("_", " ").capitalize()) for code in CUSTOM_CODES)


def custom(code):
    return f"GarageSale.{code}"


def crud(app, model, actions="view add change delete"):
    return {f"{app}.{action}_{model}" for action in actions.split()}


SPONSOR_VIEW = {"Sponsors.view_sponsor", "Contributors.view_contributions"}
SPONSOR_WORK = SPONSOR_VIEW | crud("Sponsors", "sponsor", "add change") | {"Sponsors.confirm_sponsor"} | {
    custom(code) for code in ("contact_sponsor", "email_sponsor", "generate_sponsor_pdf", "import_sponsors", "export_sponsors")}
MARKET_WORK = {"CraftMarket.view_marketer", "CraftMarket.change_marketer"} | {
    custom(code) for code in ("add_marketer", "contact_marketer", "invite_marketer", "confirm_marketer", "reject_marketer",
                              "email_marketer", "generate_marketer_pdf", "import_marketers", "export_marketers")}
TEMPLATE_WORK = crud("GarageSale", "communicationtemplate", "view add change") | crud("GarageSale", "templateattachment", "view add change")
PRIZES = crud("Contributors", "contributions", "view add change") | crud("GarageSale", "prizedrawwinner", "view add change")
PRIZE_ALLOCATION = {"Contributors.view_prize_allocation", "Contributors.change_prize_allocation"}
OWN = {custom("manage_own_team_profile")}
TEAM = OWN | {custom("access_team_pages")}
FINANCE_READ = {"Accounts.view_transaction", "Accounts.view_account", "Accounts.view_categories"}
FINANCE_WORK = FINANCE_READ | {"Accounts.upload_transaction", "Accounts.change_transaction", "Accounts.report_transaction",
                               "Accounts.view_uploadhistory", "Accounts.view_uploaderror", "Accounts.change_uploaderror",
                               "Accounts.add_uploadhistory", "Accounts.add_uploaderror", custom("close_financialyear")} | \
    crud("Accounts", "account") | crud("Accounts", "categories") | crud("Accounts", "financialyear")
EXEC = TEAM | SPONSOR_WORK | MARKET_WORK | TEMPLATE_WORK | PRIZES | crud("GarageSale", "eventdata", "view add change") | \
    crud("News", "newsarticle") | crud("News", "newslettermailinglist") | crud("GarageSale", "motd") | \
    crud("GarageSale", "supporting") | {"News.publish_news", "Accounts.report_transaction", "Location.view_location",
    "Location.change_location", "Location.add_location", "user_management.view_teammember", "user_management.generate_id_card",
    "GarageSale.delete_communicationtemplate", "GarageSale.delete_templateattachment", "GarageSale.view_nomination"} | {
        custom(code) for code in ("view_all_template_categories", "manage_all_template_categories", "export_location",
                                  "view_newsletter", "add_newsletter", "change_newsletter", "delete_newsletter", "send_newsletter")}
GROUP_PERMISSIONS = {
    "ExecMember": EXEC,
    # Redundant grants are avoided: every Officer is explicitly also an ExecMember.
    "Officer": TEAM | FINANCE_READ | {"user_management.manage_team_access"} | crud("GarageSale", "nomination", "view change"),
    "PrizeAllocationManager": TEAM | PRIZE_ALLOCATION,
    "SponsorshipManager": TEAM | SPONSOR_WORK | TEMPLATE_WORK | PRIZES | {"GarageSale.view_eventdata",
        custom("view_sponsor_templates"), custom("manage_sponsor_templates")},
    "CraftMarketManager": TEAM | MARKET_WORK | TEMPLATE_WORK | {"GarageSale.view_eventdata",
        custom("view_market_templates"), custom("manage_market_templates")},
    "Financier": TEAM | FINANCE_WORK,
    "Volunteer": OWN,
    # Populated from all project-owned permissions at deployment, excluding retired aliases.
    "WebAdmin": set(),
}

# Explicit aliases are safe to consolidate; unrelated or library permissions are never guessed.
ALIASES = {
    "user_management.manage_own_profile": "GarageSale.manage_own_team_profile",
    "GarageSale.can_create_event": "GarageSale.add_eventdata", "GarageSale.change_event": "GarageSale.change_eventdata",
    "GarageSale.can_edit_event": "GarageSale.change_eventdata", "GarageSale.view_event": "GarageSale.view_eventdata",
    "GarageSale.can_view_event": "GarageSale.view_eventdata", "GarageSale.view_eventList": "GarageSale.view_eventdata",
    "GarageSale.can_delete_event": "GarageSale.delete_eventdata", "GarageSale.can_use_event": "GarageSale.view_eventdata",
    "GarageSale.create_supporting": "GarageSale.add_supporting", "GarageSale.can_create_supporting": "GarageSale.add_supporting",
    "GarageSale.can_create_motd": "GarageSale.add_motd", "GarageSale.can_edit_motd": "GarageSale.change_motd",
    "GarageSale.can_view_motd": "GarageSale.view_motd", "GarageSale.can_delete_motd": "GarageSale.delete_motd",
    "News.can_manage_news": "News.view_newsarticle", "News.can_create_news": "News.add_newsarticle",
    "News.can_edit_news": "News.change_newsarticle", "News.change_news": "News.change_newsarticle",
    "News.can_view_news": "News.view_newsarticle", "News.view_news": "News.view_newsarticle",
    "News.can_delete_news": "News.delete_newsarticle", "News.delete_news": "News.delete_newsarticle",
    "News.publish_newsarticle": "News.publish_news", "News.can_publish_news": "News.publish_news",
    "Accounts.edit_transaction": "Accounts.change_transaction", "Accounts.view_category": "Accounts.view_categories",
    "GarageSale.edit_communicationtemplate": "GarageSale.change_communicationtemplate",
    "CraftMarket.edit_marketer": "CraftMarket.change_marketer", "CraftMarket.can_manage": "CraftMarket.change_marketer",
}
ROLE_FLAGS = {f"GarageSale.{code}" for code in ("is_team_member", "is_trustee", "is_administrator", "is_manager", "is_exec_member")}


def allowed(user, permission):
    """Use normal Django grants (including direct grants), never role-name checks."""
    return bool(user.is_authenticated and user.is_active and user.has_perm(permission))


def require(user, *permissions):
    if not all(allowed(user, permission) for permission in permissions):
        raise PermissionDenied("You do not have permission for this operation.")


def capability_required(permission):
    """Enforce direct URL access as well as navigation visibility."""
    def decorate(view):
        @wraps(view)
        def guarded(request, *args, **kwargs):
            require(request.user, permission)
            return view(request, *args, **kwargs)
        return guarded
    return decorate


TYPE_PERMISSIONS = {
    "Sponsor": {"view": "Sponsors.view_sponsor", "add": "Sponsors.add_sponsor", "change": "Sponsors.change_sponsor",
                "contact": custom("contact_sponsor"), "import": custom("import_sponsors"), "export": custom("export_sponsors")},
    "Marketer": {"view": "CraftMarket.view_marketer", "add": custom("add_marketer"), "change": "CraftMarket.change_marketer",
                 "contact": custom("contact_marketer"), "import": custom("import_marketers"), "export": custom("export_marketers")},
}


def contributor_types(user, action="view"):
    return [kind for kind, permissions in TYPE_PERMISSIONS.items() if allowed(user, permissions[action])]


def require_contributor(user, contributor, action="view"):
    permissions = TYPE_PERMISSIONS.get(contributor.contributor_type)
    if not permissions:
        raise PermissionDenied("Unsupported contributor type.")
    require(user, permissions["view"], permissions[action])


def template_categories(user, action="view"):
    """None means all categories; an empty set means no category access."""
    prefix = "view" if action == "view" else "manage"
    if allowed(user, custom(f"{prefix}_all_template_categories")):
        return None
    categories = set()
    for app, code in (("Sponsors", "sponsor"), ("CraftMarket", "market")):
        if allowed(user, custom(f"{prefix}_{code}_templates")):
            categories.add(settings.APPS_SETTINGS.get(app, {}).get("EmailTemplateCategory", app))
    return categories


def require_template(user, category, action="view"):
    require(user, f"GarageSale.{action}_communicationtemplate")
    categories = template_categories(user, "view" if action == "view" else "manage")
    if categories is not None and category not in categories:
        raise PermissionDenied("This template category is not available to you.")
