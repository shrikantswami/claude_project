from django.conf import settings

def google_ads(request):
    return {
        'GOOGLE_ADSENSE_CLIENT': getattr(settings, 'GOOGLE_ADSENSE_CLIENT', ''),
    }