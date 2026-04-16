"""
accounts/urls.py
─────────────────────────────────────────────────────────────
URL configuration for the `accounts` app.

Include this in your project's main urls.py:

    from django.urls import path, include

    urlpatterns = [
        path("accounts/", include("accounts.urls", namespace="accounts")),
        ...
    ]
"""

from django.urls import path
from django.contrib.auth import views as auth_views

from . import views

app_name = "accounts"   # namespace → use as  {% url 'accounts:login' %}

urlpatterns = [

    # ── Authentication ──────────────────────────────────────
    path(
        "login/",
        views.LoginView.as_view(),
        name="login",
    ),
    path(
        "logout/",
        views.LogoutView.as_view(),
        name="logout",
    ),
    path(
        "register/",
        views.register,
        name="register",
    ),

    # ── Dashboard (protected) ────────────────────────────────
    path(
        "dashboard/",
        views.dashboard,
        name="dashboard",
    ),

    # ── Social login stubs ───────────────────────────────────
    # Replace these with django-allauth routes once configured.
    path(
        "login/google/",
        views.google_login,
        name="google_login",
    ),
    path(
        "login/github/",
        views.github_login,
        name="github_login",
    ),

    # ── Password Reset (Django built-in views) ───────────────
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="accounts/password_reset.html",
            email_template_name="accounts/emails/password_reset_email.html",
            subject_template_name="accounts/emails/password_reset_subject.txt",
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="accounts/password_reset_done.html",
        ),
        name="password_reset_done",
    ),
    path(
        "password-reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
        ),
        name="password_reset_confirm",
    ),
    path(
        "password-reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="accounts/password_reset_complete.html",
        ),
        name="password_reset_complete",
    ),
]
