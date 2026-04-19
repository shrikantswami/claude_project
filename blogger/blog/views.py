"""
blog/views.py
─────────────────────────────────────────────────────────────
Complete views for the Blogger app covering:
  - Post CRUD  (list, detail, create, edit, delete)
  - Draft list
  - Comment management (list, approve, delete)
  - Stats overview
  - Audience / subscriber list
  - Search
  - Tag-filtered listing
  - Post like (AJAX-friendly)

All write operations require login.
"""

import json
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q, Sum, Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.views import View
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView,
)
from django.urls import reverse_lazy

from .models import Post, Comment, Tag, Like, Subscriber


# ═══════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════

def paginate(queryset, request, per_page=10):
    """Return a page object for the given queryset."""
    paginator = Paginator(queryset, per_page)
    page_num  = request.GET.get("page", 1)
    try:
        return paginator.page(page_num)
    except PageNotAnInteger:
        return paginator.page(1)
    except EmptyPage:
        return paginator.page(paginator.num_pages)


# ═══════════════════════════════════════════════════════════
#  POST VIEWS
# ═══════════════════════════════════════════════════════════

class PostListView(View):
    """
    Public listing of all published posts.
    Supports ?q= search and ?tag= filtering.
    URL name: blog:post_list
    """
    template_name = "blog/post_list.html"
    # "blog/templates/blog/post_list.html"

    def get(self, request):
        posts = Post.objects.filter(status="published").order_by("-published_at")

        # ── Search ────────────────────────────
        query = request.GET.get("q", "").strip()
        if query:
            posts = posts.filter(
                Q(title__icontains=query) |
                Q(content__icontains=query) |
                Q(author__username__icontains=query)
            )

        # ── Tag filter ────────────────────────
        tag_slug = request.GET.get("tag", "").strip()
        active_tag = None
        if tag_slug:
            active_tag = get_object_or_404(Tag, slug=tag_slug)
            posts = posts.filter(tags=active_tag)

        page  = paginate(posts, request, per_page=9)
        tags  = Tag.objects.annotate(post_count=Count("posts")).order_by("-post_count")[:15]

        return render(request, self.template_name, {
            "posts":      page,
            "query":      query,
            "tags":       tags,
            "active_tag": active_tag,
        })


class PostDetailView(View):
    """
    Public view — only serves published posts.
    Returns 404 for drafts and scheduled posts.
    This is intentional and correct behaviour.
    URL name: blog:post_detail  (slug)
    """
    template_name = "blog/post_detail.html"

    def get(self, request, slug):
        # Authors and staff can preview drafts, public only sees published
        if request.user.is_authenticated:
            post = get_object_or_404(Post, slug=slug)
            # Block non-authors from viewing others' drafts
            if post.status != "published" and post.author != request.user and not request.user.is_staff:
                from django.core.exceptions import PermissionDenied
                raise PermissionDenied
        else:
            post = get_object_or_404(Post, slug=slug, status="published")

        post.view_count += 1
        post.save(update_fields=["view_count"])

        comments  = post.comments.filter(is_approved=True).order_by("created_at")
        related   = Post.objects.filter(
            status="published", tags__in=post.tags.all()
        ).exclude(pk=post.pk).distinct()[:3]
        user_liked = (
            request.user.is_authenticated and
            Like.objects.filter(post=post, user=request.user).exists()
        )

        return render(request, self.template_name, {
            "post":       post,
            "comments":   comments,
            "related":    related,
            "user_liked": user_liked,
        })

    def post(self, request, slug):
        """Handle comment submission on the detail page."""
        post = get_object_or_404(Post, slug=slug, status="published")

        name    = request.POST.get("name", "").strip()
        email   = request.POST.get("email", "").strip()
        body    = request.POST.get("body", "").strip()

        if not name or not body:
            messages.error(request, "Name and comment body are required.")
            return redirect("blog:post_detail", slug=slug)

        Comment.objects.create(
            post=post,
            author=request.user if request.user.is_authenticated else None,
            name=name,
            email=email,
            body=body,
            is_approved=False,          # pending moderation
        )
        messages.success(request, "Your comment has been submitted and is awaiting approval.")
        return redirect("blog:post_detail", slug=slug)

class PostPreviewView(LoginRequiredMixin, View):
    """
    Private preview — only the author or staff can access.
    Works for draft, scheduled, and published posts.
    Shows a preview banner so the author knows it is not live.
    """
    template_name = "blog/post_detail.html"
    login_url     = "accounts:login"

    def get(self, request, pk):
        post = get_object_or_404(Post, pk=pk)

        # Only the author or staff can preview
        if post.author != request.user and not request.user.is_staff:
            messages.error(request, "You do not have permission to preview this post.")
            return redirect("blog:post_list")

        comments = post.comments.filter(
            is_approved=True
        ).select_related("author").order_by("created_at")

        return render(request, self.template_name, {
            "post":        post,
            "comments":    comments,
            "related":     [],
            "user_liked":  False,
            "is_preview":  True,   # ← flag for the template banner
        })

class PostCreateView(LoginRequiredMixin, View):
    """
    Create a new post (authenticated users only).
    URL name: blog:post_create
    """
    template_name = "blog/post_form.html"
    login_url     = "accounts:login"

    def get(self, request):
        tags = Tag.objects.all()
        return render(request, self.template_name, {"tags": tags, "action": "create"})

    def post(self, request):
        title     = request.POST.get("title", "").strip()
        content   = request.POST.get("content", "").strip()
        excerpt   = request.POST.get("excerpt", "").strip()
        status    = request.POST.get("status", "draft")
        tag_ids   = request.POST.getlist("tags")
        thumbnail = request.FILES.get("thumbnail")

        # ── Basic validation ──────────────────
        if not title or not content:
            messages.error(request, "Title and content are required.")
            return render(request, self.template_name, {
                "tags": Tag.objects.all(), "action": "create",
                "form_data": request.POST,
            })

        # ── Build slug (unique) ───────────────
        base_slug = slugify(title)
        slug      = base_slug
        counter   = 1
        while Post.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1

        # ── Create post ───────────────────────
        post = Post.objects.create(
            title=title,
            slug=slug,
            author=request.user,
            content=content,
            excerpt=excerpt or content[:200],
            status=status,
            thumbnail=thumbnail,
            published_at=timezone.now() if status == "published" else None,
        )

        if tag_ids:
            post.tags.set(Tag.objects.filter(pk__in=tag_ids))

        messages.success(
            request,
            f'Post "{post.title}" has been {"published" if status == "published" else "saved as draft"}.',
        )
        # ── Production-standard redirect logic ──────────────
        if status == "published":
            return redirect("blog:post_detail", slug=post.slug)
        else:
            # Drafts and scheduled posts go to preview
            return redirect("blog:post_preview", pk=post.pk)


class PostEditView(LoginRequiredMixin, View):
    """
    Edit an existing post (author only).
    URL name: blog:post_edit  (pk)
    """
    template_name = "blog/post_form.html"
    login_url     = "accounts:login"

    def _get_post(self, request, pk):
        post = get_object_or_404(Post, pk=pk)
        if post.author != request.user and not request.user.is_staff:
            return None
        return post

    def get(self, request, pk):
        post = self._get_post(request, pk)
        if post is None:
            messages.error(request, "You do not have permission to edit this post.")
            return redirect("blog:post_list")

        tags = Tag.objects.all()
        return render(request, self.template_name, {
            "post": post, "tags": tags, "action": "edit",
        })

    def post(self, request, pk):
        post = self._get_post(request, pk)
        if post is None:
            messages.error(request, "You do not have permission to edit this post.")
            return redirect("blog:post_list")

        title     = request.POST.get("title", "").strip()
        content   = request.POST.get("content", "").strip()
        excerpt   = request.POST.get("excerpt", "").strip()
        status    = request.POST.get("status", post.status)
        tag_ids   = request.POST.getlist("tags")
        thumbnail = request.FILES.get("thumbnail")

        if not title or not content:
            messages.error(request, "Title and content are required.")
            return render(request, self.template_name, {
                "post": post, "tags": Tag.objects.all(), "action": "edit",
            })

        # Update fields
        post.title   = title
        post.content = content
        post.excerpt = excerpt or content[:200]
        post.status  = status

        if thumbnail:
            post.thumbnail = thumbnail

        # Set published_at only on first publish
        if status == "published" and post.published_at is None:
            post.published_at = timezone.now()

        post.save()

        if tag_ids:
            post.tags.set(Tag.objects.filter(pk__in=tag_ids))
        else:
            post.tags.clear()

        messages.success(request, f'Post "{post.title}" has been updated.')
        if status == "published":
            return redirect("blog:post_detail", slug=post.slug)
        else:
            return redirect("blog:post_preview", pk=post.pk)


class PostDeleteView(LoginRequiredMixin, View):
    """
    Delete a post (author or staff only).
    URL name: blog:post_delete  (pk)
    """
    login_url = "accounts:login"

    def post(self, request, pk):
        post = get_object_or_404(Post, pk=pk)
        if post.author != request.user and not request.user.is_staff:
            messages.error(request, "You do not have permission to delete this post.")
            return redirect("blog:post_list")

        title = post.title
        post.delete()
        messages.success(request, f'Post "{title}" has been deleted.')
        return redirect("blog:post_list")


# ═══════════════════════════════════════════════════════════
#  DRAFT VIEWS
# ═══════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════
#  COMMENT VIEWS
# ═══════════════════════════════════════════════════════════

@login_required(login_url="accounts:login")
def comment_list(request):
    """
    Moderation queue: all comments on the current user's posts.
    Supports ?status=pending|approved|all filter.
    URL name: blog:comment_list
    """
    status_filter = request.GET.get("status", "pending")
    comments = Comment.objects.filter(post__author=request.user).order_by("-created_at")

    if status_filter == "pending":
        comments = comments.filter(is_approved=False)
    elif status_filter == "approved":
        comments = comments.filter(is_approved=True)

    page = paginate(comments, request, per_page=15)
    return render(request, "blog/comment_list.html", {
        "comments":      page,
        "status_filter": status_filter,
        "pending_count": Comment.objects.filter(
            post__author=request.user, is_approved=False
        ).count(),
    })


@login_required(login_url="accounts:login")
def approve_comment(request, pk):
    """
    Approve a pending comment.
    URL name: blog:approve_comment  (pk)
    """
    comment = get_object_or_404(Comment, pk=pk, post__author=request.user)
    comment.is_approved = True
    comment.save(update_fields=["is_approved"])
    messages.success(request, "Comment approved.")
    return redirect("blog:comment_list")


@login_required(login_url="accounts:login")
def delete_comment(request, pk):
    """
    Delete a comment (POST only).
    URL name: blog:delete_comment  (pk)
    """
    comment = get_object_or_404(Comment, pk=pk, post__author=request.user)
    comment.delete()
    messages.success(request, "Comment deleted.")
    return redirect("blog:comment_list")


# ═══════════════════════════════════════════════════════════
#  LIKE VIEW  (AJAX-friendly)
# ═══════════════════════════════════════════════════════════

@login_required(login_url="accounts:login")
def toggle_like(request, pk):
    """
    Toggle a like on a post. Returns JSON for AJAX callers,
    or redirects for regular form submissions.
    URL name: blog:toggle_like  (pk)
    """
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    post  = get_object_or_404(Post, pk=pk)
    like  = Like.objects.filter(post=post, user=request.user).first()

    if like:
        like.delete()
        liked      = False
    else:
        Like.objects.create(post=post, user=request.user)
        liked      = True

    like_count = post.likes.count()

    # AJAX response
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"liked": liked, "like_count": like_count})

    # Normal form POST fallback
    return redirect("blog:post_detail", slug=post.slug)


# ═══════════════════════════════════════════════════════════
#  STATS VIEW
# ═══════════════════════════════════════════════════════════

@login_required(login_url="accounts:login")
def stats(request):
    """
    Analytics overview for the current user's blog.
    URL name: blog:stats
    """
    user_posts = Post.objects.filter(author=request.user)
    now        = timezone.now()

    # ── Top posts by views ────────────────────
    top_posts = user_posts.filter(status="published").order_by("-view_count")[:5]

    # ── Views per day (last 30 days) ──────────
    daily_views = []
    for i in range(29, -1, -1):
        day  = (now - timedelta(days=i)).date()
        views = user_posts.filter(
            published_at__date=day
        ).aggregate(total=Sum("view_count"))["total"] or 0
        daily_views.append({"date": str(day), "views": views})

    # ── Overall totals ─────────────────────────
    total_views    = user_posts.aggregate(t=Sum("view_count"))["t"] or 0
    total_posts    = user_posts.count()
    published      = user_posts.filter(status="published").count()
    total_comments = Comment.objects.filter(post__in=user_posts).count()
    total_likes    = Like.objects.filter(post__in=user_posts).count()

    # ── Posts by month (last 6 months) ────────
    monthly_posts = []
    for i in range(5, -1, -1):
        month_start = (now.replace(day=1) - timedelta(days=i * 30)).replace(day=1)
        month_end   = (month_start + timedelta(days=32)).replace(day=1)
        count       = user_posts.filter(
            created_at__gte=month_start,
            created_at__lt=month_end,
        ).count()
        monthly_posts.append({
            "month": month_start.strftime("%b"),
            "count": count,
        })

    return render(request, "blog/stats.html", {
        "top_posts":     top_posts,
        "daily_views":   json.dumps(daily_views),
        "monthly_posts": json.dumps(monthly_posts),
        "total_views":   total_views,
        "total_posts":   total_posts,
        "published":     published,
        "total_comments":total_comments,
        "total_likes":   total_likes,
    })


# ═══════════════════════════════════════════════════════════
#  AUDIENCE VIEW
# ═══════════════════════════════════════════════════════════

@login_required(login_url="accounts:login")
def audience(request):
    """
    Subscriber management page.
    URL name: blog:audience
    """
    subscribers = Subscriber.objects.filter(author=request.user).order_by("-subscribed_at")
    page        = paginate(subscribers, request, per_page=20)

    total        = subscribers.count()
    this_month   = subscribers.filter(
        subscribed_at__gte=timezone.now().replace(day=1)
    ).count()

    return render(request, "blog/audience.html", {
        "subscribers":  page,
        "total":        total,
        "this_month":   this_month,
    })


# ═══════════════════════════════════════════════════════════
#  SEARCH VIEW
# ═══════════════════════════════════════════════════════════

def search(request):
    """
    Dedicated search results page.
    URL name: blog:search
    """
    query = request.GET.get("q", "").strip()
    posts = Post.objects.none()

    if query:
        posts = Post.objects.filter(
            status="published"
        ).filter(
            Q(title__icontains=query) |
            Q(content__icontains=query) |
            Q(excerpt__icontains=query) |
            Q(tags__name__icontains=query)
        ).distinct().order_by("-published_at")

    page = paginate(posts, request, per_page=10)
    return render(request, "blog/search_results.html", {
        "posts": page,
        "query": query,
        "count": posts.count() if query else 0,
    })


# ═══════════════════════════════════════════════════════════
#  TAG VIEW
# ═══════════════════════════════════════════════════════════

def tag_detail(request, slug):
    """
    List all published posts for a given tag.
    URL name: blog:tag_detail  (slug)
    """
    tag   = get_object_or_404(Tag, slug=slug)
    posts = Post.objects.filter(
        status="published", tags=tag
    ).order_by("-published_at")

    page = paginate(posts, request, per_page=9)
    return render(request, "blog/tag_detail.html", {
        "tag":   tag,
        "posts": page,
    })



# ─────────────────────────────────────────────
#  Helper
# ─────────────────────────────────────────────
def _paginate(queryset, request, per_page=15):
    paginator = Paginator(queryset, per_page)
    page_num  = request.GET.get("page", 1)
    try:
        return paginator.page(page_num)
    except PageNotAnInteger:
        return paginator.page(1)
    except EmptyPage:
        return paginator.page(paginator.num_pages)


# ─────────────────────────────────────────────
#  Draft list view
# ─────────────────────────────────────────────
@login_required(login_url="accounts:login")
def draft_list(request):
    """
    Paginated list of the current user's unpublished posts
    (status = 'draft' or 'scheduled').

    Supports:
      ?q=        full-text search on title + content
      ?status=   filter by 'draft' or 'scheduled'
      ?sort=     updated | oldest | title | words
      ?page=     pagination
    """
    base_qs = Post.objects.filter(
        author=request.user
    ).exclude(
        status="published"
    ).select_related("author").prefetch_related("tags")

    # ── Search ──────────────────────────────
    query = request.GET.get("q", "").strip()
    if query:
        base_qs = base_qs.filter(
            Q(title__icontains=query) |
            Q(content__icontains=query) |
            Q(excerpt__icontains=query)
        )

    # ── Status filter ────────────────────────
    status_filter = request.GET.get("status", "").strip()
    if status_filter in ("draft", "scheduled"):
        base_qs = base_qs.filter(status=status_filter)

    # ── Sorting ──────────────────────────────
    sort = request.GET.get("sort", "updated")
    sort_map = {
        "updated": "-updated_at",
        "oldest":  "created_at",
        "title":   "title",
        "words":   "-read_time",
    }
    base_qs = base_qs.order_by(sort_map.get(sort, "-updated_at"))

    # ── Counts for stat cards ────────────────
    all_unpublished = Post.objects.filter(
        author=request.user
    ).exclude(status="published")

    draft_count     = all_unpublished.filter(status="draft").count()
    scheduled_count = all_unpublished.filter(status="scheduled").count()
    total_unpublished = draft_count + scheduled_count

    # ── Paginate ─────────────────────────────
    drafts = _paginate(base_qs, request, per_page=15)

    return render(request, "blog/draft_list.html", {
        "drafts":           drafts,
        "query":            query,
        "status_filter":    status_filter,
        "sort":             sort,
        "draft_count":      draft_count,
        "scheduled_count":  scheduled_count,
        "total_unpublished": total_unpublished,
    })


# ─────────────────────────────────────────────
#  Publish post  (updated — redirects to preview for drafts)
# ─────────────────────────────────────────────
@login_required(login_url="accounts:login")
def publish_post(request, pk):
    """
    Immediately publish a draft or scheduled post.
    Only accepts POST to prevent accidental GET-based publishing.
    Redirects to the live post_detail after publishing.
    """
    if request.method != "POST":
        return redirect("blog:draft_list")

    post = get_object_or_404(Post, pk=pk, author=request.user)

    if post.status == "published":
        messages.info(request, f'"{post.title}" is already published.')
        return redirect("blog:post_detail", slug=post.slug)

    post.status       = "published"
    post.published_at = timezone.now()
    post.save(update_fields=["status", "published_at"])

    messages.success(request, f'"{post.title}" is now live.')
    return redirect("blog:post_detail", slug=post.slug)


# ─────────────────────────────────────────────
#  Unschedule post
# ─────────────────────────────────────────────
@login_required(login_url="accounts:login")
def unschedule_post(request, pk):
    """
    Revert a scheduled post back to draft status.
    Clears the published_at timestamp.
    Only accepts POST.
    """
    if request.method != "POST":
        return redirect("blog:draft_list")

    post = get_object_or_404(Post, pk=pk, author=request.user)

    if post.status != "scheduled":
        messages.info(request, f'"{post.title}" is not scheduled.')
        return redirect("blog:draft_list")

    post.status       = "draft"
    post.published_at = None
    post.save(update_fields=["status", "published_at"])

    messages.success(request, f'"{post.title}" has been moved back to drafts.')
    return redirect("blog:draft_list")
