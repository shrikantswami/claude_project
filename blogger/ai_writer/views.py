"""
ai_writer/views.py
────────────────────────────────────────────────────────────
Views:
  generator()          GET  → show the generation form
                       POST → call Claude, save GeneratedPost, redirect to review
  review()             GET  → review generated content, edit inline
                       POST → save edits back to GeneratedPost
  push_to_blog()       POST → create a real blog Post from the GeneratedPost
  generated_list()     GET  → list all generated posts
  delete_generated()   POST → delete a GeneratedPost
  regenerate()         POST → re-run Claude on an existing GeneratedPost

URL names (add to ai_writer/urls.py):
  ai_writer:generator
  ai_writer:review         (pk)
  ai_writer:push_to_blog   (pk)
  ai_writer:list
  ai_writer:delete         (pk)
  ai_writer:regenerate     (pk)
"""

import json
import anthropic

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify

from .models import GeneratedPost


# ─────────────────────────────────────────────
#  Word-count targets
# ─────────────────────────────────────────────
LENGTH_TARGETS = {
    "short":    500,
    "medium":   1200,
    "long":     2000,
    "deepdive": 3000,
}


# ─────────────────────────────────────────────
#  Build the Claude prompt
# ─────────────────────────────────────────────
def _build_prompt(gp: GeneratedPost) -> str:
    """
    Construct the system + user prompt for Claude.
    Returns a single user message string.
    """
    word_target = LENGTH_TARGETS.get(gp.length, 1200)

    tone_desc = {
        "technical":      "precise and technical — use correct terminology, include specifics",
        "conversational": "friendly and conversational — write as if talking to a colleague",
        "tutorial":       "step-by-step tutorial style — numbered steps, clear instructions",
        "opinion":        "opinionated editorial — take a clear stance, argue a perspective",
    }.get(gp.tone, "technical")

    audience_desc = {
        "beginner":     "complete beginners — explain every concept, avoid jargon",
        "intermediate": "intermediate developers — assume basic familiarity, skip basics",
        "senior":       "senior engineers — skip fundamentals, go deep on nuances",
        "general":      "a general tech audience — keep it accessible but informative",
    }.get(gp.audience, "intermediate developers")

    code_instruction = (
        "Include relevant, production-quality code examples in Markdown fenced code blocks."
        if gp.include_code
        else "Do NOT include code examples — focus on concepts and explanations only."
    )

    key_points_section = ""
    if gp.key_points.strip():
        key_points_section = f"\nKey points to cover:\n{gp.key_points}\n"

    extra_section = ""
    if gp.extra_instructions.strip():
        extra_section = f"\nAdditional instructions:\n{gp.extra_instructions}\n"

    tags_section = ""
    if gp.tags_input.strip():
        tags_section = f"\nThe post should be tagged with: {gp.tags_input}"

    prompt = f"""You are an expert technical blogger. Write a complete, high-quality blog post for the following topic.

Topic: {gp.topic}
Target audience: {audience_desc}
Tone: {tone_desc}
Target length: approximately {word_target} words
{key_points_section}{extra_section}{tags_section}

{code_instruction}

Your response MUST be valid JSON with exactly these fields:
{{
  "title": "The final, compelling post title",
  "excerpt": "A 1-2 sentence summary for post listings (max 200 chars)",
  "content": "The full blog post content in Markdown format",
  "tags": "comma-separated list of 3-6 relevant tags"
}}

Requirements for the content:
- Use ## for section headings, ### for subsections
- Write in flowing paragraphs, not bullet-point lists
- Include a strong introduction that hooks the reader
- Include a practical conclusion with key takeaways
- Use > blockquote syntax for important callouts or quotes
- {f'Include ```language fenced code blocks for all code examples' if gp.include_code else 'No code blocks'}
- Aim for exactly {word_target} words in the content field
- Do NOT include the title in the content — it is a separate field

Return ONLY the JSON object. No preamble, no explanation, no markdown wrapper."""

    return prompt


# ─────────────────────────────────────────────
#  Call Claude API
# ─────────────────────────────────────────────
def _call_claude(prompt: str, model: str = "claude-sonnet-4-20250514") -> dict:
    """
    Call the Anthropic API and return parsed JSON.
    Raises ValueError on bad response.
    """
    client   = anthropic.Anthropic()
    message  = client.messages.create(
        model      = model,
        max_tokens = 8192,
        messages   = [{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude returned invalid JSON: {e}\n\nRaw response:\n{raw[:500]}")

    required = {"title", "excerpt", "content", "tags"}
    missing  = required - set(data.keys())
    if missing:
        raise ValueError(f"Claude response missing fields: {missing}")

    return data


# ─────────────────────────────────────────────
#  Generator view
# ─────────────────────────────────────────────
@login_required(login_url="accounts:login")
def generator(request):
    """
    GET  → render the generation form
    POST → call Claude, save result, redirect to review
    """
    if request.method == "GET":
        return render(request, "ai_writer/generator.html", {
            "length_choices":   GeneratedPost.LENGTH_CHOICES,
            "tone_choices":     GeneratedPost.TONE_CHOICES,
            "audience_choices": GeneratedPost.AUDIENCE_CHOICES,
        })

    # ── POST: validate inputs ─────────────────
    topic = request.POST.get("topic", "").strip()
    if not topic:
        messages.error(request, "Topic / title is required.")
        return render(request, "ai_writer/generator.html", {
            "length_choices":   GeneratedPost.LENGTH_CHOICES,
            "tone_choices":     GeneratedPost.TONE_CHOICES,
            "audience_choices": GeneratedPost.AUDIENCE_CHOICES,
            "form_data":        request.POST,
        })

    # ── Create the GeneratedPost record ───────
    gp = GeneratedPost.objects.create(
        author             = request.user,
        topic              = topic,
        key_points         = request.POST.get("key_points", "").strip(),
        audience           = request.POST.get("audience", "intermediate"),
        tone               = request.POST.get("tone", "technical"),
        length             = request.POST.get("length", "medium"),
        tags_input         = request.POST.get("tags_input", "").strip(),
        include_code       = request.POST.get("include_code") == "yes",
        extra_instructions = request.POST.get("extra_instructions", "").strip(),
        status             = GeneratedPost.STATUS_PENDING,
    )

    # ── Call Claude ───────────────────────────
    try:
        prompt = _build_prompt(gp)
        data   = _call_claude(prompt)

        gp.generated_title   = data["title"]
        gp.generated_excerpt = data["excerpt"]
        gp.generated_content = data["content"]
        gp.generated_tags    = data["tags"]
        gp.status            = GeneratedPost.STATUS_GENERATED
        gp.save()

        messages.success(request, f'Post generated: "{gp.generated_title}"')
        return redirect("ai_writer:review", pk=gp.pk)

    except Exception as e:
        gp.status    = GeneratedPost.STATUS_FAILED
        gp.error_msg = str(e)
        gp.save()

        messages.error(request, f"Generation failed: {e}")
        return redirect("ai_writer:review", pk=gp.pk)


# ─────────────────────────────────────────────
#  Review view
# ─────────────────────────────────────────────
@login_required(login_url="accounts:login")
def review(request, pk):
    """
    GET  → display generated post with inline editing
    POST → save edits back to the GeneratedPost
    """
    gp = get_object_or_404(GeneratedPost, pk=pk, author=request.user)

    if request.method == "POST":
        gp.generated_title   = request.POST.get("title",   gp.generated_title).strip()
        gp.generated_excerpt = request.POST.get("excerpt", gp.generated_excerpt).strip()
        gp.generated_content = request.POST.get("content", gp.generated_content).strip()
        gp.generated_tags    = request.POST.get("tags",    gp.generated_tags).strip()
        gp.save()
        messages.success(request, "Changes saved.")
        return redirect("ai_writer:review", pk=gp.pk)

    return render(request, "ai_writer/review.html", {"gp": gp})


# ─────────────────────────────────────────────
#  Push to blog
# ─────────────────────────────────────────────
@login_required(login_url="accounts:login")
def push_to_blog(request, pk):
    """
    POST → create a real blog.Post from the GeneratedPost.
    Accepts ?action=draft or ?action=publish in query string.
    """
    if request.method != "POST":
        return redirect("ai_writer:review", pk=pk)

    gp     = get_object_or_404(GeneratedPost, pk=pk, author=request.user)
    action = request.POST.get("action", "draft")

    if gp.blog_post:
        messages.info(request, "This post has already been pushed to the blog.")
        return redirect("blog:post_edit", pk=gp.blog_post.pk)

    if not gp.generated_title or not gp.generated_content:
        messages.error(request, "Cannot push — the generated content is empty.")
        return redirect("ai_writer:review", pk=pk)

    from blog.models import Post, Tag

    # ── Build unique slug ─────────────────────
    base_slug = slugify(gp.generated_title)
    slug      = base_slug
    counter   = 1
    while Post.objects.filter(slug=slug).exists():
        slug = f"{base_slug}-{counter}"
        counter += 1

    # ── Determine status ──────────────────────
    status       = "published" if action == "publish" else "draft"
    published_at = timezone.now() if status == "published" else None

    # ── Create the Post ───────────────────────
    post = Post.objects.create(
        title        = gp.generated_title,
        slug         = slug,
        author       = request.user,
        content      = gp.generated_content,
        excerpt      = gp.generated_excerpt,
        status       = status,
        published_at = published_at,
    )

    # ── Attach tags ───────────────────────────
    if gp.generated_tags:
        for tag_name in gp.generated_tags.split(","):
            tag_name = tag_name.strip()
            if tag_name:
                tag, _ = Tag.objects.get_or_create(
                    slug=slugify(tag_name),
                    defaults={"name": tag_name},
                )
                post.tags.add(tag)

    # ── Link back ─────────────────────────────
    gp.blog_post = post
    gp.status    = GeneratedPost.STATUS_PUBLISHED if status == "published" else GeneratedPost.STATUS_DRAFT
    gp.save(update_fields=["blog_post", "status"])

    messages.success(
        request,
        f'"{post.title}" has been {"published" if status == "published" else "saved as draft"} in the blog.'
    )

    return redirect("blog:post_edit", pk=post.pk)


# ─────────────────────────────────────────────
#  Generated post list
# ─────────────────────────────────────────────
@login_required(login_url="accounts:login")
def generated_list(request):
    """
    Paginated list of all GeneratedPosts for the logged-in user.
    """
    qs = GeneratedPost.objects.filter(author=request.user).order_by("-created_at")

    # Status filter
    status = request.GET.get("status", "")
    if status:
        qs = qs.filter(status=status)

    paginator = Paginator(qs, 15)
    page_num  = request.GET.get("page", 1)
    try:
        page = paginator.page(page_num)
    except (EmptyPage, PageNotAnInteger):
        page = paginator.page(1)

    return render(request, "ai_writer/list.html", {
        "generated_posts": page,
        "status_filter":   status,
        "status_choices":  GeneratedPost.STATUS_CHOICES,
    })


# ─────────────────────────────────────────────
#  Delete generated post
# ─────────────────────────────────────────────
@login_required(login_url="accounts:login")
def delete_generated(request, pk):
    """POST only — delete a GeneratedPost."""
    if request.method != "POST":
        return redirect("ai_writer:list")

    gp = get_object_or_404(GeneratedPost, pk=pk, author=request.user)
    gp.delete()
    messages.success(request, "Generated post deleted.")
    return redirect("ai_writer:list")


# ─────────────────────────────────────────────
#  Regenerate
# ─────────────────────────────────────────────
@login_required(login_url="accounts:login")
def regenerate(request, pk):
    """
    POST only — re-run Claude on an existing GeneratedPost,
    overwriting the previous output.
    """
    if request.method != "POST":
        return redirect("ai_writer:review", pk=pk)

    gp        = get_object_or_404(GeneratedPost, pk=pk, author=request.user)
    gp.status = GeneratedPost.STATUS_PENDING
    gp.save(update_fields=["status"])

    try:
        prompt = _build_prompt(gp)
        data   = _call_claude(prompt)

        gp.generated_title   = data["title"]
        gp.generated_excerpt = data["excerpt"]
        gp.generated_content = data["content"]
        gp.generated_tags    = data["tags"]
        gp.status            = GeneratedPost.STATUS_GENERATED
        gp.error_msg         = ""
        gp.save()

        messages.success(request, "Post regenerated successfully.")

    except Exception as e:
        gp.status    = GeneratedPost.STATUS_FAILED
        gp.error_msg = str(e)
        gp.save()
        messages.error(request, f"Regeneration failed: {e}")

    return redirect("ai_writer:review", pk=pk)