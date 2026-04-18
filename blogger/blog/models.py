"""
blog/models.py
─────────────────────────────────────────────────────────────
Models:
  Tag          — post categories / keywords
  Post         — the main blog post
  Comment      — user comments on posts
  Like         — one like per user per post
  Subscriber   — email subscribers per author
"""

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


# ─────────────────────────────────────────────
#  Tag
# ─────────────────────────────────────────────
class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=60, unique=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


# ─────────────────────────────────────────────
#  Post
# ─────────────────────────────────────────────
class Post(models.Model):
    STATUS_CHOICES = [
        ("draft",     "Draft"),
        ("published", "Published"),
        ("scheduled", "Scheduled"),
    ]

    title        = models.CharField(max_length=255)
    slug         = models.SlugField(max_length=270, unique=True, blank=True)
    author       = models.ForeignKey(User, on_delete=models.CASCADE, related_name="posts")
    content      = models.TextField()
    excerpt      = models.TextField(max_length=500, blank=True)
    thumbnail    = models.ImageField(upload_to="thumbnails/%Y/%m/", blank=True, null=True)
    tags         = models.ManyToManyField(Tag, blank=True, related_name="posts")
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    view_count   = models.PositiveIntegerField(default=0)
    read_time    = models.PositiveSmallIntegerField(default=1, help_text="Estimated read time in minutes")
    published_at = models.DateTimeField(null=True, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Auto-generate slug from title if not set
        if not self.slug:
            base_slug = slugify(self.title)
            slug      = base_slug
            counter   = 1
            while Post.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug

        # Auto-calculate read time (~200 words per minute)
        word_count   = len(self.content.split())
        self.read_time = max(1, round(word_count / 200))

        # Set published_at when first published
        if self.status == "published" and self.published_at is None:
            self.published_at = timezone.now()

        super().save(*args, **kwargs)

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse("blog:post_detail", kwargs={"slug": self.slug})

    @property
    def like_count(self):
        return self.likes.count()

    @property
    def comment_count(self):
        return self.comments.filter(is_approved=True).count()

    def get_status_display_pill(self):
        mapping = {
            "published": "Published",
            "draft":     "Draft",
            "scheduled": "Scheduled",
        }
        return mapping.get(self.status, self.status.capitalize())


# ─────────────────────────────────────────────
#  Comment
# ─────────────────────────────────────────────
class Comment(models.Model):
    post        = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    author      = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="comments")
    name        = models.CharField(max_length=100)
    email       = models.EmailField(blank=True)
    body        = models.TextField()
    is_approved = models.BooleanField(default=False)
    is_read     = models.BooleanField(default=False)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Comment by {self.name} on '{self.post.title}'"


# ─────────────────────────────────────────────
#  Like
# ─────────────────────────────────────────────
class Like(models.Model):
    post       = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="likes")
    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name="likes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("post", "user")   # one like per user per post

    def __str__(self):
        return f"{self.user.username} liked '{self.post.title}'"


# ─────────────────────────────────────────────
#  Subscriber
# ─────────────────────────────────────────────
class Subscriber(models.Model):
    author        = models.ForeignKey(User, on_delete=models.CASCADE, related_name="subscribers")
    email         = models.EmailField()
    subscribed_at = models.DateTimeField(auto_now_add=True)
    is_active     = models.BooleanField(default=True)

    class Meta:
        unique_together = ("author", "email")
        ordering        = ["-subscribed_at"]

    def __str__(self):
        return f"{self.email} → {self.author.username}"
from django.db import models

# Create your models here.
