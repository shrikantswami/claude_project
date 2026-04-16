from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views import View


# ─────────────────────────────────────────────
#  Login View
# ─────────────────────────────────────────────
class LoginView(View):
    """Handles GET (show form) and POST (authenticate user)."""

    template_name = "accounts/login.html"

    def get(self, request):
        # Redirect already-authenticated users to the dashboard
        if request.user.is_authenticated:
            return redirect("dashboard")

        form = AuthenticationForm()
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        form = AuthenticationForm(request, data=request.POST)

        if form.is_valid():
            username = form.cleaned_data.get("username")
            password = form.cleaned_data.get("password")
            user = authenticate(request, username=username, password=password)

            if user is not None:
                login(request, user)

                # Handle "Remember me"
                if not request.POST.get("remember_me"):
                    # Session expires when the browser closes
                    request.session.set_expiry(0)
                else:
                    # Session lasts 30 days
                    request.session.set_expiry(60 * 60 * 24 * 30)

                messages.success(request, f"Welcome back, {user.get_full_name() or username}!")

                # Honour the ?next= redirect (e.g. from @login_required)
                next_url = request.POST.get("next") or request.GET.get("next")
                return redirect(next_url if next_url else "dashboard")

            else:
                messages.error(request, "Invalid username or password.")
        else:
            messages.error(request, "Please correct the errors below.")

        return render(request, self.template_name, {"form": form})


# ─────────────────────────────────────────────
#  Logout View
# ─────────────────────────────────────────────
class LogoutView(View):
    """Logs the user out and redirects to the login page."""

    def get(self, request):
        logout(request)
        messages.info(request, "You have been logged out successfully.")
        return redirect("accounts:login")

    # Support POST logout too (more secure — use a form with CSRF token)
    def post(self, request):
        logout(request)
        messages.info(request, "You have been logged out successfully.")
        return redirect("accounts:login")


# ─────────────────────────────────────────────
#  Dashboard (protected example)
# ─────────────────────────────────────────────
@login_required(login_url="accounts:login")
def dashboard(request):
    """Example protected view — replace with your real dashboard."""
    return render(request, "accounts/dashboard.html", {"user": request.user})


# ─────────────────────────────────────────────
#  Social login stubs (replace with allauth)
# ─────────────────────────────────────────────
def google_login(request):
    """
    Placeholder — integrate with django-allauth for real OAuth.
    Install:  pip install django-allauth
    Docs:     https://django-allauth.readthedocs.io/
    """
    messages.info(request, "Google login is not configured yet.")
    return redirect("accounts:login")


def github_login(request):
    """
    Placeholder — integrate with django-allauth for real OAuth.
    """
    messages.info(request, "GitHub login is not configured yet.")
    return redirect("accounts:login")


# ─────────────────────────────────────────────
#  Register stub
# ─────────────────────────────────────────────
def register(request):
    """Placeholder — wire up your registration form here."""
    return render(request, "accounts/register.html")


# ─────────────────────────────────────────────
#  Password reset stub
# ─────────────────────────────────────────────
def password_reset(request):
    """
    Use Django's built-in password reset views or override here.
    Built-in: django.contrib.auth.views.PasswordResetView
    """
    from django.contrib.auth.views import PasswordResetView
    return PasswordResetView.as_view()(request)
