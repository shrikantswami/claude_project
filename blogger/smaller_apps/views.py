from django.shortcuts import render

def index(request):
    return render(request, 'smaller_apps/index.html')