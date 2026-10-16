"""Route-level policy gates for management pages, including function-based views."""
from django.core.exceptions import PermissionDenied
from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404
from django.utils.deprecation import MiddlewareMixin

from GarageSale.access_policy import custom, require, require_template


class AccessPolicyMiddleware(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        match = request.resolver_match
        namespace, name = match.namespace, match.url_name
        permission = None
        if namespace == "GoogleDrive":
            permission = custom("access_drive")
        elif namespace == "TeamPages":
            fixed = {"Root": custom("access_team_pages"), "EventRoot": custom("access_team_pages"),
                     "EventList": "GarageSale.view_eventdata", "Event": "GarageSale.view_eventdata",
                     "EventDisplay": "GarageSale.view_eventdata", "EventView": "GarageSale.view_eventdata",
                     "EventUse": "GarageSale.view_eventdata", "EventCreate": "GarageSale.add_eventdata",
                     "EventEdit": "GarageSale.change_eventdata", "News": "News.view_newsarticle",
                     "CreateNews": "News.add_newsarticle", "EditNews": "News.change_newsarticle",
                     "ViewNews": "News.view_newsarticle", "PublishNews": "News.publish_news",
                     "DeleteNews": "News.delete_newsarticle", "MOTDList": "GarageSale.view_motd",
                     "MotdCreate": "GarageSale.add_motd", "MotdEdit": "GarageSale.change_motd",
                     "MotdView": "GarageSale.view_motd", "MotdDelete": "GarageSale.delete_motd",
                     "GoogleDriveEntryPoint": custom("access_drive"), "SponsorEntryPoint": "Sponsors.view_sponsor",
                     "ContributionBoard": "Contributors.view_contributions", "PrizeDrawWinners": "GarageSale.view_prizedrawwinner"}
            permission = fixed.get(name)
            if permission is None and not name.startswith("CommunicationTemplate"):
                raise PermissionDenied("No access policy is defined for this management route.")
            if name in {"PublishNews", "MotdDelete"} and request.method != "POST":
                return HttpResponseNotAllowed(["POST"])
        elif namespace == "Account":
            fixed = {"EntryPoint": "Accounts.report_transaction", "report": "Accounts.report_transaction",
                     "TransactionList": "Accounts.view_transaction", "CategoryList": "Accounts.view_categories",
                     "upload_transactions": "Accounts.upload_transaction", "UploadErrorList": "Accounts.view_uploaderror",
                     "get_categories": "Accounts.view_transaction", "get_child_categories": "Accounts.view_transaction",
                     "edit_transaction": "Accounts.change_transaction", "edit_split": "Accounts.change_transaction",
                     "delete_transaction": "Accounts.delete_transaction", "FinancialYearList": "Accounts.view_financialyear",
                     "FinancialYearDetail": "Accounts.view_financialyear", "FinancialYearEdit": "Accounts.change_financialyear",
                     "FinancialYearCreate": "Accounts.add_financialyear", "FinancialYearClose": custom("close_financialyear")}
            permission = fixed.get(name)
            if permission is None:
                raise PermissionDenied("No access policy is defined for this Accounts route.")
            if name == "FinancialYearClose" and request.method != "POST":
                return HttpResponseNotAllowed(["POST"])
        elif namespace == "CraftMarket":
            if name == "EntryPoint":
                permission = "CraftMarket.view_marketer"
            elif name != "ContributorRSVP" and not name.startswith("template"):
                raise PermissionDenied("No access policy is defined for this CraftMarket route.")
            if name == "template_duplicate" and request.method != "POST":
                return HttpResponseNotAllowed(["POST"])
        elif namespace == "Location":
            if name in {"EventStats", "EventAdBoard"}:
                permission = "Location.view_location"
            elif name == "EventAdBoardDownload":
                permission = custom("export_location")
            elif name == "AddLocation":
                permission = "Location.add_location"
            elif name in {"update", "delete", "confirm"}:
                from Location.models import Location
                location = (Location.get_by_ext_id(view_kwargs["ext_id"]) if "ext_id" in view_kwargs
                            else get_object_or_404(Location, pk=view_kwargs["pk"]))
                if location is not None and location.user_id != getattr(request.user, "pk", None):
                    permission = "Location.change_location"
        elif namespace == "user_management":
            if name == "team_member_id_cards":
                permission = "user_management.generate_id_card"
            elif name in {"profile", "profile_edit"}:
                from user_management.models import TeamMember
                member_id = view_kwargs.get("team_member_id")
                member = get_object_or_404(TeamMember, team_member_id=member_id) if member_id else None
                own = member is None or member.user_id == getattr(request.user, "pk", None)
                permission = custom("manage_own_team_profile") if own else (
                    "user_management.change_teammember" if name == "profile_edit" else "user_management.view_teammember")
        if permission:
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            require(request.user, permission)
        if ((namespace == "TeamPages" and name.startswith("CommunicationTemplate")) or
                (namespace == "CraftMarket" and name.startswith("template"))):
            from GarageSale.models import CommunicationTemplate
            action = ("delete" if "Delete" in name or "delete" in name else
                      "add" if "Create" in name or "create" in name or "Duplicate" in name or "duplicate" in name else
                      "change" if "Edit" in name or "edit" in name else "view")
            identity = view_kwargs.get("pk", view_kwargs.get("template_id"))
            if identity:
                template = get_object_or_404(CommunicationTemplate, pk=identity)
                require_template(request.user, template.category, "view")
                require_template(request.user, template.category, action)
            elif action != "view":
                category = request.POST.get("category", request.GET.get("category", ""))
                if namespace == "CraftMarket":
                    category = "CraftMarket"
                require_template(request.user, category, action)
        return None
