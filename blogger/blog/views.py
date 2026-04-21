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
import re
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from django.shortcuts import render
from django.utils.html import escape
from django.utils.safestring import mark_safe




import csv
import json
from datetime import timedelta, date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q, Sum, Count, Avg
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.views import View
from django.http import HttpResponse
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

def subscribe(request):
    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        if email:
            Subscriber.objects.get_or_create(
                email=email,
                author=request.user if request.user.is_authenticated else None,
            )
            messages.success(request, "You're subscribed! Thanks for joining.")
        else:
            messages.error(request, "Please enter a valid email address.")
    return redirect("home")

class HomeView(View):
    template_name = "blog/home.html"

    def get(self, request):
        # Logged-in authors go straight to dashboard
        if request.user.is_authenticated:
            return redirect("accounts:dashboard")

        # Public visitors see the blog landing page
        latest_posts = Post.objects.filter(
            status="published"
        ).select_related("author").prefetch_related("tags").order_by("-published_at")[:6]

        featured_post = Post.objects.filter(
            status="published"
        ).select_related("author").order_by("-view_count").first()

        from django.db.models import Count
        popular_tags = Tag.objects.annotate(
            post_count=Count("posts")
        ).filter(post_count__gt=0).order_by("-post_count")[:10]

        return render(request, self.template_name, {
            "latest_posts":  latest_posts,
            "featured_post": featured_post,
            "popular_tags":  popular_tags,
        })

"""
Stats view — add/replace in blog/views.py
────────────────────────────────────────────────────────────
Provides a full analytics overview for the logged-in author.

Supports ?range= query param:
    7   → last 7 days
    30  → last 30 days  (default)
    90  → last 90 days
    all → all time

Context variables passed to stats.html:
    selected_range      str   '7' | '30' | '90' | 'all'
    period_label        str   e.g. "Last 30 days"
    range_start         date
    range_end           date

    total_views         int
    total_posts         int
    total_comments      int
    total_likes         int
    posts_this_period   int   posts published in the selected range
    new_comments        int   comments received today
    views_change        int   % change vs previous period (signed)
    views_change_abs    int   abs(views_change)
    likes_change        int   change in likes count vs prev period (signed)
    likes_change_abs    int   abs(likes_change)

    top_posts           QuerySet  top 5 by view_count
    avg_views_per_post  int
    avg_read_time       int   minutes
    comment_rate        str   e.g. "1.5"
    like_rate           str   e.g. "6.8"
    most_active_tag     str   name of the most-used tag
    total_words         int   total word count across all posts

    daily_labels        JSON  list of date strings for views line chart
    daily_views_data    JSON  list of view counts per day
    monthly_labels      JSON  list of month labels for bar chart
    monthly_counts      JSON  list of post counts per month
"""




@login_required(login_url="accounts:login")
def stats(request):

    # ── Date range ────────────────────────────────────────────
    selected_range = request.GET.get("range", "30")
    now            = timezone.now()
    today          = now.date()

    if selected_range == "7":
        range_days   = 7
        period_label = "Last 7 days"
        range_start  = today - timedelta(days=6)
    elif selected_range == "90":
        range_days   = 90
        period_label = "Last 90 days"
        range_start  = today - timedelta(days=89)
    elif selected_range == "all":
        range_days   = None
        period_label = "All time"
        first_post   = Post.objects.filter(
            author=request.user, status="published"
        ).order_by("published_at").first()
        range_start  = first_post.published_at.date() if first_post else today
    else:
        selected_range = "30"
        range_days   = 30
        period_label = "Last 30 days"
        range_start  = today - timedelta(days=29)

    range_end = today

    # ── Base querysets ────────────────────────────────────────
    all_posts = Post.objects.filter(
        author=request.user, status="published"
    ).prefetch_related("tags")

    if range_days:
        period_posts = all_posts.filter(published_at__date__gte=range_start)
        prev_start   = range_start - timedelta(days=range_days)
        prev_posts   = all_posts.filter(
            published_at__date__gte=prev_start,
            published_at__date__lt=range_start,
        )
    else:
        period_posts = all_posts
        prev_posts   = Post.objects.none()

    all_comments = Comment.objects.filter(post__author=request.user)
    all_likes    = Like.objects.filter(post__author=request.user)

    # ── Stat card values ──────────────────────────────────────
    total_posts    = all_posts.count()
    total_views    = all_posts.aggregate(t=Sum("view_count"))["t"] or 0
    total_comments = all_comments.count()
    total_likes    = all_likes.count()
    posts_this_period = period_posts.count()
    new_comments   = all_comments.filter(created_at__date=today).count()

    # Views change vs previous period
    period_views = period_posts.aggregate(t=Sum("view_count"))["t"] or 0
    prev_views   = prev_posts.aggregate(t=Sum("view_count"))["t"] or 0
    if prev_views > 0:
        views_change = round(((period_views - prev_views) / prev_views) * 100)
    else:
        views_change = 0
    views_change_abs = abs(views_change)

    # Likes change vs previous period
    period_likes = Like.objects.filter(
        post__author=request.user,
        created_at__date__gte=range_start,
    ).count() if range_days else total_likes
    prev_likes = Like.objects.filter(
        post__author=request.user,
        created_at__date__gte=range_start - timedelta(days=range_days) if range_days else today,
        created_at__date__lt=range_start,
    ).count() if range_days else 0
    likes_change     = period_likes - prev_likes
    likes_change_abs = abs(likes_change)

    # ── Top 5 posts ───────────────────────────────────────────
    top_posts = all_posts.order_by("-view_count")[:5]

    # ── Quick summary stats ───────────────────────────────────
    avg_views_per_post = round(total_views / total_posts) if total_posts else 0

    avg_read_time_raw  = all_posts.aggregate(a=Avg("read_time"))["a"]
    avg_read_time      = round(avg_read_time_raw) if avg_read_time_raw else 0

    comment_rate = (
        round((total_comments / total_views) * 100, 1) if total_views else 0
    )
    like_rate = (
        round((total_likes / total_views) * 100, 1) if total_views else 0
    )

    # Most active tag (tag with most published posts by this author)
    most_active_tag_obj = (
        Tag.objects.filter(posts__author=request.user, posts__status="published")
        .annotate(cnt=Count("posts"))
        .order_by("-cnt")
        .first()
    )
    most_active_tag = most_active_tag_obj.name if most_active_tag_obj else "—"

    # Total words written
    total_words = sum(
        len(p.content.split()) for p in all_posts
    )

    # ── Daily views chart data (line chart) ───────────────────
    # Show daily breakdown for the selected period
    chart_days = range_days if range_days else min(
        (today - range_start).days + 1, 90
    )
    chart_days = min(chart_days, 90)   # cap at 90 data points

    daily_labels     = []
    daily_views_data = []

    for i in range(chart_days - 1, -1, -1):
        day = today - timedelta(days=i)
        day_views = all_posts.filter(
            published_at__date=day
        ).aggregate(t=Sum("view_count"))["t"] or 0

        if chart_days <= 14:
            label = day.strftime("%b %d")
        elif chart_days <= 60:
            label = day.strftime("%b %d")
        else:
            label = day.strftime("%b %d")

        daily_labels.append(label)
        daily_views_data.append(day_views)

    # ── Monthly posts chart data (bar chart) ──────────────────
    monthly_labels = []
    monthly_counts = []

    for i in range(5, -1, -1):
        # Go back i full months from the current month
        if now.month - i > 0:
            m_month = now.month - i
            m_year  = now.year
        else:
            m_month = now.month - i + 12
            m_year  = now.year - 1

        count = all_posts.filter(
            published_at__year=m_year,
            published_at__month=m_month,
        ).count()

        monthly_labels.append(
            date(m_year, m_month, 1).strftime("%b")
        )
        monthly_counts.append(count)

    # ── Build context ─────────────────────────────────────────
    context = {
        # Range controls
        "selected_range": selected_range,
        "period_label":   period_label,
        "range_start":    range_start,
        "range_end":      range_end,

        # Stat cards
        "total_views":        f"{total_views:,}" if total_views >= 1000 else total_views,
        "total_posts":        total_posts,
        "total_comments":     total_comments,
        "total_likes":        total_likes,
        "posts_this_period":  posts_this_period,
        "new_comments":       new_comments,
        "views_change":       views_change,
        "views_change_abs":   views_change_abs,
        "likes_change":       likes_change,
        "likes_change_abs":   likes_change_abs,

        # Top posts
        "top_posts":           top_posts,

        # Quick summary
        "avg_views_per_post":  avg_views_per_post,
        "avg_read_time":       avg_read_time,
        "comment_rate":        comment_rate,
        "like_rate":           like_rate,
        "most_active_tag":     most_active_tag,
        "total_words":         f"{total_words:,}",

        # Chart data — JSON-serialisable
        "daily_labels":      json.dumps(daily_labels),
        "daily_views_data":  json.dumps(daily_views_data),
        "monthly_labels":    json.dumps(monthly_labels),
        "monthly_counts":    json.dumps(monthly_counts),
    }

    return render(request, "blog/stats.html", context)

# ─────────────────────────────────────────────
#  Audience view
# ─────────────────────────────────────────────
@login_required(login_url="accounts:login")
def audience(request):
    """
    Subscriber management page.
    Supports:
      ?q=      email search
      ?status= active | inactive
      ?page=   pagination
      ?export=csv  → triggers CSV download
    """

    # ── CSV export ───────────────────────────
    if request.GET.get("export") == "csv":
        return export_audience_csv(request)

    # ── Base queryset ────────────────────────
    all_subs = Subscriber.objects.filter(
        author=request.user
    ).order_by("-subscribed_at")

    # ── Search ───────────────────────────────
    query = request.GET.get("q", "").strip()
    if query:
        all_subs = all_subs.filter(email__icontains=query)

    # ── Status filter ────────────────────────
    status_filter = request.GET.get("status", "").strip()
    if status_filter == "active":
        all_subs = all_subs.filter(is_active=True)
    elif status_filter == "inactive":
        all_subs = all_subs.filter(is_active=False)

    # ── Paginate ─────────────────────────────
    subscribers = _paginate(all_subs, request, per_page=20)

    # ── Stat card values ─────────────────────
    base = Subscriber.objects.filter(author=request.user)

    total          = base.count()
    active_count   = base.filter(is_active=True).count()
    inactive_count = base.filter(is_active=False).count()
    retention_rate = round((active_count / total) * 100, 1) if total else 0

    now            = timezone.now()
    month_start    = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_month_end = month_start - timedelta(seconds=1)
    last_month_start = (last_month_end.replace(day=1))

    new_this_month  = base.filter(subscribed_at__gte=month_start).count()
    new_last_month  = base.filter(
        subscribed_at__gte=last_month_start,
        subscribed_at__lt=month_start,
    ).count()
    month_change    = new_this_month - new_last_month
    growth_rate     = round((new_this_month / active_count) * 100, 1) if active_count else 0

    # ── Monthly breakdown (last 6 months) ────
    monthly_labels    = []
    monthly_counts    = []
    monthly_breakdown = []
    max_count         = 1

    for i in range(5, -1, -1):
        if now.month - i > 0:
            m_month = now.month - i
            m_year  = now.year
        else:
            m_month = now.month - i + 12
            m_year  = now.year - 1

        count = base.filter(
            subscribed_at__year=m_year,
            subscribed_at__month=m_month,
        ).count()

        label = date(m_year, m_month, 1).strftime("%b %Y")
        monthly_labels.append(date(m_year, m_month, 1).strftime("%b"))
        monthly_counts.append(count)
        monthly_breakdown.append({"label": label, "count": count, "pct": 0})
        max_count = max(max_count, count)

    # Calculate bar widths as percentage of the best month
    for item in monthly_breakdown:
        item["pct"] = round((item["count"] / max_count) * 100) if max_count else 0

    # Best month label
    best_idx   = monthly_counts.index(max(monthly_counts)) if monthly_counts else -1
    best_month = monthly_breakdown[best_idx]["label"] if best_idx >= 0 and max(monthly_counts) > 0 else None

    # Avg per month
    avg_per_month = round(sum(monthly_counts) / len(monthly_counts)) if monthly_counts else 0

    return render(request, "blog/audience.html", {
        # Paginated list
        "subscribers":    subscribers,
        "query":          query,
        "status_filter":  status_filter,

        # Stat cards
        "total":          total,
        "active_count":   active_count,
        "inactive_count": inactive_count,
        "retention_rate": retention_rate,
        "new_this_month": new_this_month,
        "month_change":   month_change,
        "growth_rate":    growth_rate,

        # Right sidebar
        "monthly_breakdown": monthly_breakdown,
        "best_month":     best_month,
        "avg_per_month":  avg_per_month,

        # Chart data (JSON)
        "monthly_labels": json.dumps(monthly_labels),
        "monthly_counts": json.dumps(monthly_counts),
    })


# ─────────────────────────────────────────────
#  Remove subscriber
# ─────────────────────────────────────────────
@login_required(login_url="accounts:login")
def remove_subscriber(request, pk):
    """
    Mark a subscriber as inactive (soft delete).
    Only accepts POST.
    """
    if request.method != "POST":
        return redirect("blog:audience")

    subscriber = get_object_or_404(Subscriber, pk=pk, author=request.user)
    subscriber.is_active = False
    subscriber.save(update_fields=["is_active"])

    messages.success(request, f"{subscriber.email} has been removed from your subscribers.")
    return redirect("blog:audience")


# ─────────────────────────────────────────────
#  Export CSV
# ─────────────────────────────────────────────
@login_required(login_url="accounts:login")
def export_audience_csv(request):
    """
    Download all active subscribers as a CSV file.
    Triggered by ?export=csv on the audience page.
    """
    subscribers = Subscriber.objects.filter(
        author=request.user, is_active=True
    ).order_by("-subscribed_at")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="subscribers.csv"'

    writer = csv.writer(response)
    writer.writerow(["Email", "Subscribed at", "Status"])

    for sub in subscribers:
        writer.writerow([
            sub.email,
            sub.subscribed_at.strftime("%Y-%m-%d %H:%M"),
            "Active" if sub.is_active else "Inactive",
        ])

    return response


# ─────────────────────────────────────────────
#  Highlight helper
# ─────────────────────────────────────────────
def _highlight(text, query, max_chars=200):
    """
    Return a short snippet of `text` with `query` terms wrapped in <mark>.
    Tries to centre the snippet around the first match.
    """
    if not text or not query:
        return text

    safe_text  = escape(text)
    terms      = [re.escape(t) for t in query.split() if len(t) > 1]
    if not terms:
        return safe_text[:max_chars]

    pattern = re.compile(r'(' + '|'.join(terms) + r')', re.IGNORECASE)

    # Find first match position for snippet centering
    match = pattern.search(safe_text)
    if match:
        start = max(0, match.start() - 60)
        end   = min(len(safe_text), start + max_chars)
        snippet = ('…' if start > 0 else '') + safe_text[start:end] + ('…' if end < len(safe_text) else '')
    else:
        snippet = safe_text[:max_chars] + ('…' if len(safe_text) > max_chars else '')

    # Wrap matches in <mark>
    highlighted = pattern.sub(r'<mark>\1</mark>', snippet)
    return mark_safe(highlighted)


# ─────────────────────────────────────────────
#  Search view
# ─────────────────────────────────────────────
def search(request):
    """
    Full-text search across published posts.
    No login required — public page.
    """
    query       = request.GET.get("q", "").strip()
    filter_type = request.GET.get("filter", "").strip()
    sort        = request.GET.get("sort", "relevance").strip()

    posts_qs    = Post.objects.none()
    count       = 0
    related_tags= Tag.objects.none()
    suggestions = []

    if query:
        base = Post.objects.filter(
            status="published"
        ).select_related("author").prefetch_related("tags")

        # ── Apply field filter ────────────────
        if filter_type == "title":
            base = base.filter(title__icontains=query)

        elif filter_type == "tags":
            base = base.filter(tags__name__icontains=query).distinct()

        else:
            # Search across all fields
            base = base.filter(
                Q(title__icontains=query)   |
                Q(content__icontains=query) |
                Q(excerpt__icontains=query) |
                Q(tags__name__icontains=query) |
                Q(author__first_name__icontains=query) |
                Q(author__last_name__icontains=query)
            ).distinct()

        # ── Apply sort ───────────────────────
        if sort == "latest":
            base = base.order_by("-published_at")
        elif sort == "views":
            base = base.order_by("-view_count")
        else:
            # Default: sort by relevance — title matches first, then content
            # Django ORM doesn't have native relevance scoring, so we
            # approximate by putting title-matching posts first.
            from django.db.models import Case, When, IntegerField
            base = base.annotate(
                relevance=Case(
                    When(title__icontains=query, then=2),
                    When(excerpt__icontains=query, then=1),
                    default=0,
                    output_field=IntegerField(),
                )
            ).order_by("-relevance", "-published_at")

        count    = base.count()
        posts_qs = base

        # ── Attach highlighted fields ─────────
        # We add highlighted_title and highlighted_excerpt as Python
        # attributes rather than using Django template filters so the
        # template can render them with |safe cleanly.
        post_list = list(posts_qs[:200])   # materialise for annotation
        for post in post_list:
            post.highlighted_title   = _highlight(post.title,   query, max_chars=120)
            post.highlighted_excerpt = _highlight(
                post.excerpt or post.content, query, max_chars=220
            )
        # Re-wrap as a list for pagination (we already sliced for safety)
        posts_qs = post_list

        # ── Related tags ──────────────────────
        related_tags = Tag.objects.filter(
            name__icontains=query
        ).order_by("name")[:8]

        # ── Search suggestions ────────────────
        suggestions = _build_suggestions(query)

    # ── Popular posts (sidebar) ───────────────
    popular_posts = Post.objects.filter(
        status="published"
    ).select_related("author").order_by("-view_count")[:5]

    # ── Paginate ─────────────────────────────
    paginator = Paginator(posts_qs, 10)
    page_num  = request.GET.get("page", 1)
    try:
        posts_page = paginator.page(page_num)
    except (PageNotAnInteger, EmptyPage):
        posts_page = paginator.page(1)

    return render(request, "blog/search_results.html", {
        "query":        query,
        "count":        count,
        "posts":        posts_page,
        "filter_type":  filter_type,
        "sort":         sort,
        "related_tags": related_tags,
        "suggestions":  suggestions,
        "popular_posts":popular_posts,
    })


# ─────────────────────────────────────────────
#  Suggestion builder
# ─────────────────────────────────────────────
def _build_suggestions(query):
    """
    Generate up to 5 search suggestions based on:
    1. Matching tag names
    2. Partial title words from existing posts
    These are shown in the sidebar when no results are found
    and as "Try searching for" prompts.
    """
    suggestions = set()

    # Tags that partially match the query
    for tag in Tag.objects.filter(name__icontains=query)[:4]:
        suggestions.add(tag.name)

    # Words from post titles that contain the query
    posts_with_match = Post.objects.filter(
        status="published",
        title__icontains=query,
    ).values_list("title", flat=True)[:10]

    for title in posts_with_match:
        words = title.split()
        for word in words:
            clean = re.sub(r'[^\w\s]', '', word).strip()
            if (
                query.lower() in clean.lower() and
                len(clean) > 3 and
                clean.lower() != query.lower()
            ):
                suggestions.add(clean)

    # Add some fixed related searches if the query looks like Django-related
    django_hints = ["Django", "Python", "REST API", "deployment", "testing", "Celery"]
    if len(suggestions) < 4:
        for hint in django_hints:
            if hint.lower() != query.lower() and len(suggestions) < 5:
                suggestions.add(hint)

    return sorted(suggestions)[:5]

