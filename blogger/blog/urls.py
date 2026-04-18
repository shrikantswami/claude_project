

from django.urls import path
from django.contrib.auth import views as auth_views

from . import views
# blog/urls.py
urlpatterns = [
path("posts/",        views.post_list,    name="post_list"),
path("posts/new/",    views.post_create,  name="post_create"),
path("posts/drafts/", views.draft_list,   name="draft_list"),
path("comments/",     views.comment_list, name="comment_list"),
path("stats/",        views.stats,        name="stats"),
path("audience/",     views.audience,     name="audience"),
]