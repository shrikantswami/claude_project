from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from .models import Post

class PostSitemap(Sitemap):
    changefreq = 'weekly'
    priority = 0.9

    def items(self):
        # only published posts
        return Post.objects.filter(status='published').order_by('-created_at')

    def lastmod(self, obj):
        return obj.updated_at  # or created_at if you don't have updated_at

    def location(self, obj):
        return reverse('blog:post_detail', args=[obj.slug])


class StaticViewSitemap(Sitemap):
    changefreq = 'monthly'
    priority = 0.5

    def items(self):
        return ['blog:post_list', 'accounts:login']

    def location(self, item):
        return reverse(item)