import json
from datetime import timedelta, date

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views import View
from django.utils import timezone
from django import forms


# ─────────────────────────────────────────────
#  Custom Registration Form
# ─────────────────────────────────────────────
class RegisterForm(UserCreationForm):
    first_name = forms.CharField(max_length=30, required=True)
    last_name  = forms.CharField(max_length=30, required=True)
    email      = forms.EmailField(required=True)

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
        return render(request, self.template_name, {"form": RegisterForm()})

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
    template_name = "accounts/login.html"

    def get(self, request):
        if request.user.is_authenticated:
            return redirect("accounts:dashboard")
        return render(request, self.template_name, {"form": AuthenticationForm()})

    def post(self, request):
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = authenticate(
                request,
                username=form.cleaned_data.get("username"),
                password=form.cleaned_data.get("password"),
            )
            if user:
                login(request, user)
                request.session.set_expiry(0 if not request.POST.get("remember_me") else 60 * 60 * 24 * 30)
                messages.success(request, f"Welcome back, {user.get_full_name() or user.username}!")
                next_url = request.POST.get("next") or request.GET.get("next")
                return redirect(next_url or "accounts:dashboard")
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

    def post(self, request):
        logout(request)
        messages.info(request, "You have been logged out successfully.")
        return redirect("accounts:login")


# ─────────────────────────────────────────────
#  Dashboard View
# ─────────────────────────────────────────────
@login_required(login_url="accounts:login")
def dashboard(request):
    """
    Main dashboard view.
    Replace the placeholder querysets below with your real Post / Comment /
    Subscriber models once those apps are set up.
    """
    from blog.models import Post, Comment   # import your real models here

    now        = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0)
    week_start  = now - timedelta(days=7)

    # ── Stat card values ──────────────────────
    user_posts = Post.objects.filter(author=request.user)

    total_posts      = user_posts.count()
    posts_this_month = user_posts.filter(created_at__gte=month_start).count()

    total_views   = sum(p.view_count for p in user_posts)
    last_month_views = sum(
        p.view_count for p in user_posts.filter(
            created_at__gte=now - timedelta(days=60),
            created_at__lt=now - timedelta(days=30),
        )
    )
    views_change = round(
        ((total_views - last_month_views) / max(last_month_views, 1)) * 100
    )

    total_comments  = Comment.objects.filter(post__author=request.user).count()
    new_comments    = Comment.objects.filter(
        post__author=request.user,
        created_at__date=now.date(),
    ).count()
    unread_comments = Comment.objects.filter(
        post__author=request.user, is_read=False
    ).exists()

    # ── Recent posts (latest 5) ───────────────
    recent_posts = user_posts.order_by("-created_at")[:5]

    # ── Weekly views chart data ───────────────
    # Returns a list of 7 dicts: [{"views": N}, ...]  Mon→Sun
    weekly_views = []
    for i in range(6, -1, -1):
        day = now.date() - timedelta(days=i)
        day_views = sum(
            p.view_count
            for p in user_posts.filter(created_at__date=day)
        )
        weekly_views.append({"views": day_views})

    # ── Recent activity ───────────────────────
    # Replace with your real Activity / Notification model
    recent_activity = []   # e.g. Activity.objects.filter(user=request.user).order_by("-created_at")[:8]

    # ── Subscriber stats ─────────────────────
    # Replace with your Subscriber model
    total_subscribers   = 0
    subscribers_change  = 0

    context = {
        "user":               request.user,
        # stat cards
        "total_posts":        total_posts,
        "posts_this_month":   posts_this_month,
        "total_views":        f"{total_views:,}" if total_views >= 1000 else total_views,
        "views_change":       views_change,
        "total_comments":     total_comments,
        "new_comments":       new_comments,
        "unread_comments":    unread_comments,
        "total_subscribers":  total_subscribers,
        "subscribers_change": abs(subscribers_change),
        # tables / feeds
        "recent_posts":       recent_posts,
        "recent_activity":    recent_activity,
        # chart — JSON-serialisable list for the inline <script>
        "weekly_views":       json.dumps(weekly_views),
    }
    return render(request, "accounts/dashboard.html", context)


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

@login_required(login_url="accounts:login")
def profile(request):
    return render(request, "accounts/profile.html", {"user": request.user})

@login_required(login_url="accounts:login")
def settings_view(request):          # avoid naming it "settings" — conflicts with Django's settings module
    return render(request, "accounts/settings.html", {"user": request.user})
