"""
ai_writer/urls.py
────────────────────────────────────────────────────────────
Include in blogger/urls.py:
    path("ai/", include("ai_writer.urls", namespace="ai_writer")),
"""

from django.urls import path
from . import views

app_name = "ai_writer"

urlpatterns = [
    path("",                          views.generator,       name="generator"),
    path("list/",                     views.generated_list,  name="list"),
    path("review/<int:pk>/",          views.review,          name="review"),
    path("push/<int:pk>/",            views.push_to_blog,    name="push_to_blog"),
    path("delete/<int:pk>/",          views.delete_generated,name="delete"),
    path("regenerate/<int:pk>/",      views.regenerate,      name="regenerate"),
]