"""
Legal pages — views.py  (add to blogger/views.py or a new legal/views.py)
────────────────────────────────────────────────────────────
Covers:
  terms()    → Terms of Service  →  /terms/
  privacy()  → Privacy Policy    →  /privacy/

Add to blogger/urls.py:
    from . import views as project_views

    urlpatterns = [
        ...
        path("terms/",   project_views.terms,   name="terms"),
        path("privacy/", project_views.privacy, name="privacy"),
    ]

Context variables injected into both templates:
    last_updated    str   human-readable date, e.g. "April 25, 2026"
    version         str   document version, e.g. "1.0"
    jurisdiction    str   governing jurisdiction
    contact_email   str   legal contact address
    site_url        str   canonical site URL
"""

from django.shortcuts import render
from django.utils.timezone import now

# ─────────────────────────────────────────────
#  Shared legal context
# ─────────────────────────────────────────────
LEGAL_CONTEXT = {
    "last_updated": "April 25, 2026",
    "version": "1.0",
    "jurisdiction": "England and Wales",
    "contact_email": "legal@yourdomain.com",
    "site_url": "https://yourdomain.com",
}


# ─────────────────────────────────────────────
#  Terms of Service
# ─────────────────────────────────────────────
def terms(request):
    """
    Public Terms of Service page.
    URL name: terms
    Template: templates/terms.html
    """
    return render(request, "terms.html", LEGAL_CONTEXT)


# ─────────────────────────────────────────────
#  Privacy Policy  (stub — generate separately)
# ─────────────────────────────────────────────
def privacy(request):
    """
    Public Privacy Policy page.
    URL name: privacy
    Template: templates/privacy.html
    """
    return render(request, "privacy.html", LEGAL_CONTEXT)

