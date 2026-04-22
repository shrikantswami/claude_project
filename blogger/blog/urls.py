"""
blog/urls.py
─────────────────────────────────────────────────────────────
URL configuration for the `blog` app.

Include in your project's main urls.py:

    urlpatterns = [
        path("blog/", include("blog.urls", namespace="blog")),
    ]
"""

from django.urls import path
from . import views

app_name = "blog"

urlpatterns = [

    # ── Public post listing & detail ────────────────────────
    path(
        "",
        views.PostListView.as_view(),
        name="post_list",
    ),
    path(
        "post/new/",
        views.PostCreateView.as_view(),
        name="post_create",
    ),
    path(
        "post/<slug:slug>/",
        views.PostDetailView.as_view(),
        name="post_detail",
    ),
    path("post/<int:pk>/preview/", views.PostPreviewView.as_view(), name="post_preview"),
    path("post/<int:pk>/unschedule/", views.unschedule_post, name="unschedule_post"),

    # ── Post CRUD (login required) ───────────────────────────

    path(
        "post/<int:pk>/edit/",
        views.PostEditView.as_view(),
        name="post_edit",
    ),
    path(
        "post/<int:pk>/delete/",
        views.PostDeleteView.as_view(),
        name="post_delete",
    ),
    path(
        "post/<int:pk>/publish/",
        views.publish_post,
        name="publish_post",
    ),

    # ── Drafts ───────────────────────────────────────────────
    path(
        "drafts/",
        views.draft_list,
        name="draft_list",
    ),

    # ── Likes (AJAX-friendly POST) ───────────────────────────
    path(
        "post/<int:pk>/like/",
        views.toggle_like,
        name="toggle_like",
    ),

    # ── Comments (moderation) ───────────────────────────────
    path(
        "comments/",
        views.comment_list,
        name="comment_list",
    ),
    path(
        "comments/<int:pk>/approve/",
        views.approve_comment,
        name="approve_comment",
    ),
    path(
        "comments/<int:pk>/delete/",
        views.delete_comment,
        name="delete_comment",
    ),

    # ── Analytics ────────────────────────────────────────────
    path(
        "stats/",
        views.stats,
        name="stats",
    ),

    # ── Audience / subscribers ───────────────────────────────
    path(
        "audience/",
        views.audience,
        name="audience",
    ),

    # ── Search ───────────────────────────────────────────────
    path(
        "search/",
        views.search,
        name="search",
    ),

    # ── Tag filter ────────────────────────────────────────────
    path(
        "tag/<slug:slug>/",
        views.tag_detail,
        name="tag_detail",
    ),
    path("subscribe/", views.subscribe, name="subscribe"),
    path("audience/subscriber/<int:pk>/remove/",
     views.remove_subscriber,
     name="remove_subscriber"),
    path("comments/approve-all/", views.approve_all_comments, name="approve_all_comments"),

]
