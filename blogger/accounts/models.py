from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

class UserProfile(models.Model):
    user     = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    bio      = models.TextField(max_length=300, blank=True)
    website  = models.URLField(blank=True)
    location = models.CharField(max_length=100, blank=True)
    twitter  = models.CharField(max_length=50, blank=True)
    avatar   = models.ImageField(upload_to='avatars/', blank=True, null=True)

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)