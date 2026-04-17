from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views import View
from django import forms


# ─────────────────────────────────────────────
#  Custom Registration Form
# ─────────────────────────────────────────────
class RegisterForm(UserCreationForm):
    first_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={"placeholder": "Jane"}),
    )
    last_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={"placeholder": "Doe"}),
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={"placeholder": "jane@example.com"}),
    )

    class Meta:
        model  = User
        fields = ["first_name", "last_name", "username", "email", "password1", "password2"]

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_username(self):
        username = self.cleaned_data.get("username")
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("This username is already taken.")
        return username


# ─────────────────────────────────────────────
#  Register View
# ─────────────────────────────────────────────
class RegisterView(View):
    template_name = "accounts/register.html"

    def get(self, request):
        if request.user.is_authenticated:
            return redirect("accounts:dashboard")
        form = RegisterForm()
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.first_name = form.cleaned_data["first_name"]
            user.last_name  = form.cleaned_data["last_name"]
            user.email      = form.cleaned_data["email"]
            user.save()
            login(request, user)
            messages.success(request, f"Welcome to Blogger, {user.first_name}! Your account has been created.")
            return redirect("accounts:dashboard")
        return render(request, self.template_name, {"form": form})


# ─────────────────────────────────────────────
#  Login View
# ─────────────────────────────────────────────
class LoginView(View):
    """Handles GET (show form) and POST (authenticate user)."""

    template_name = "accounts/login.html"

    def get(self, request):
        if request.user.is_authenticated:
            return redirect("accounts:dashboard")
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
                return redirect(next_url if next_url else "accounts:dashboard")
            else:
                messages.error(request, "Invalid username or password.")
        else:
            messages.error(request, "Please correct the errors below.")

        return render(request, self.template_name, {"form": form})


# ─────────────────────────────────────────────
#  Logout View
# ─────────────────────────────────────────────
class LogoutView(View):
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
#  Dashboard (protected)
# ─────────────────────────────────────────────
@login_required(login_url="accounts:login")
def dashboard(request):
    return render(request, "accounts/dashboard.html", {"user": request.user})


# ─────────────────────────────────────────────
#  Social login stubs
# ─────────────────────────────────────────────
def google_login(request):
    messages.info(request, "Google login is not configured yet.")
    return redirect("accounts:login")

def github_login(request):
    messages.info(request, "GitHub login is not configured yet.")
    return redirect("accounts:login")


# ─────────────────────────────────────────────
#  Password reset (Django built-in)
# ─────────────────────────────────────────────
def password_reset(request):
    from django.contrib.auth.views import PasswordResetView
    return PasswordResetView.as_view()(request)
