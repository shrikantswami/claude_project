"""
ai_writer/models.py
────────────────────────────────────────────────────────────
Stores every AI generation request and its output so the user
can review, edit, and push to the blog app at any time.
"""

from django.contrib.auth.models import User
from django.db import models
from django.utils.text import slugify


class GeneratedPost(models.Model):

    # ── Status choices ──────────────────────
    STATUS_PENDING   = "pending"
    STATUS_GENERATED = "generated"
    STATUS_FAILED    = "failed"
    STATUS_PUBLISHED = "published"
    STATUS_DRAFT     = "draft"

    STATUS_CHOICES = [
        (STATUS_PENDING,   "Pending"),
        (STATUS_GENERATED, "Generated"),
        (STATUS_FAILED,    "Failed"),
        (STATUS_PUBLISHED, "Published to blog"),
        (STATUS_DRAFT,     "Saved as draft"),
    ]

    # ── Tone choices ────────────────────────
    TONE_CHOICES = [
        ("technical",      "Technical"),
        ("conversational", "Conversational"),
        ("tutorial",       "Tutorial / step-by-step"),
        ("opinion",        "Opinion / editorial"),
    ]

    # ── Length choices ──────────────────────
    LENGTH_CHOICES = [
        ("short",    "Short (~500 words)"),
        ("medium",   "Medium (~1,200 words)"),
        ("long",     "Long (~2,000 words)"),
        ("deepdive", "Deep-dive (~3,000 words)"),
    ]

    # ── Audience choices ────────────────────
    AUDIENCE_CHOICES = [
        ("beginner",      "Beginner developers"),
        ("intermediate",  "Intermediate developers"),
        ("senior",        "Senior / expert developers"),
        ("general",       "General audience"),
    ]

    # ── Input fields (what the user provides) ──
    author          = models.ForeignKey(User, on_delete=models.CASCADE, related_name="generated_posts")
    topic           = models.CharField(max_length=255, help_text="The topic or desired title")
    key_points      = models.TextField(blank=True, help_text="Comma-separated points to cover")
    audience        = models.CharField(max_length=20, choices=AUDIENCE_CHOICES, default="intermediate")
    tone            = models.CharField(max_length=20, choices=TONE_CHOICES, default="technical")
    length          = models.CharField(max_length=20, choices=LENGTH_CHOICES, default="medium")
    tags_input      = models.CharField(max_length=200, blank=True, help_text="Comma-separated tags")
    include_code    = models.BooleanField(default=True)
    extra_instructions = models.TextField(blank=True, help_text="Any extra notes for the AI")

    # ── Output fields (what the AI produces) ──
    generated_title   = models.CharField(max_length=255, blank=True)
    generated_excerpt = models.TextField(blank=True)
    generated_content = models.TextField(blank=True)
    generated_tags    = models.CharField(max_length=300, blank=True)

    # ── Metadata ──────────────────────────
    status      = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    error_msg   = models.TextField(blank=True)
    word_count  = models.PositiveIntegerField(default=0)
    model_used  = models.CharField(max_length=80, default="claude-sonnet-4-20250514")
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    # ── Link to blog post once pushed ──────
    blog_post   = models.OneToOneField(
        "blog.Post",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="generated_from",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.topic} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        if self.generated_content:
            self.word_count = len(self.generated_content.split())
        super().save(*args, **kwargs)