"""
URL configuration for blogger project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from blog.views import HomeView
from . import views as project_views

from django.contrib.sitemaps.views import sitemap
from blog.sitemap import PostSitemap, StaticViewSitemap

sitemaps = {
    'posts': PostSitemap,
    'static': StaticViewSitemap,
}


urlpatterns = [
    path('admin/', admin.site.urls),
    path("accounts/", include("accounts.urls", namespace="accounts")),
    path('blog/',     include('blog.urls',     namespace='blog')),
    path("", HomeView.as_view(), name="home"),
    path("ai/", include("ai_writer.urls", namespace="ai_writer")),
    # ── Legal pages ────────────────────────────
    path("terms/", project_views.terms, name="terms"),  # ← add
    path("privacy/", project_views.privacy, name="privacy"),  # ← add
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='sitemap'),
    path('smaller-apps/', include('smaller_apps.urls')),

]
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)