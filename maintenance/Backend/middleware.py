from django.shortcuts import redirect
from django.http import JsonResponse
from django.urls import reverse

from .login_config import LOGIN_ROLES


def get_user_role(user):
    """Utility to resolve user role across predefined and registered users."""
    if not user or not user.is_authenticated:
        return None
    role = LOGIN_ROLES.get(user.username)
    if not role:
        group = user.groups.first() if hasattr(user, 'groups') else None
        if group:
            role = group.name
        elif user.is_superuser or user.username == 'Developer':
            role = "Developer"
        elif user.is_staff or user.username == 'admin':
            role = "Customer"
        else:
            role = "Maintenance Man"
    return role


##############################################################################
# Class Name : LoginMiddleware
#
# Parameters : get_response - The next Django step to run for this request.
#
# Note : Sends visitors to the login page until they sign in.
##############################################################################
class LoginMiddleware:
    """Send visitors to the login page until they sign in."""

    ##############################################################################
    # Function Name : __init__
    #
    # Parameters    : get_response - The next Django step to run.
    #
    # Note          : Saves the next step for each request.
    ##############################################################################
    def __init__(self, get_response):
        self.get_response = get_response

    ##############################################################################
    # Function Name : __call__
    #
    # Parameters    : request - The current web request.
    #
    # Note          : Requires a signed-in user before opening app pages.
    ##############################################################################
    def __call__(self, request):
        login_path = reverse("login")

        if request.path_info == login_path:
            return self.get_response(request)

        if not request.user.is_authenticated:
            return redirect(login_path)

        role = get_user_role(request.user)

        if request.path_info.startswith("/simulator/") and role != "Developer":
            return redirect("dashboard")

        if request.path_info == "/api/simulate/" and role != "Developer":
            return JsonResponse({"success": False, "error": "Developer access is required."}, status=403)

        if request.path_info.startswith("/andon/") and role not in {"Maintenance Man", "Developer"}:
            return redirect("dashboard")

        if request.path_info.startswith("/preventive-maintenance/") and role not in {"Maintenance Man", "Developer"}:
            return redirect("dashboard")

        return self.get_response(request)
