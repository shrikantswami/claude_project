from django.contrib import admin
from .models import Post, Comment, Tag, Like, Subscriber

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display  = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ["name"]

@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display   = ["title", "author", "status", "published_at", "view_count"]
    list_filter    = ["status", "author"]
    search_fields  = ["title", "content"]
    prepopulated_fields = {"slug": ("title",)}
    filter_horizontal   = ["tags"]

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display  = ["name", "post", "is_approved", "created_at"]
    list_filter   = ["is_approved"]
    search_fields = ["name", "body"]
    actions       = ["approve_comments"]

    def approve_comments(self, request, queryset):
        queryset.update(is_approved=True)
    approve_comments.short_description = "Approve selected comments"

@admin.register(Like)
class LikeAdmin(admin.ModelAdmin):
    list_display = ["user", "post", "created_at"]

@admin.register(Subscriber)
class SubscriberAdmin(admin.ModelAdmin):
    list_display = ["email", "author", "subscribed_at", "is_active"]