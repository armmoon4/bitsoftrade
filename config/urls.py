"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # path('admin/', admin.site.urls),

    # ── Authentication
    path('api/auth/', include('accounts.urls')),

    # ── Core Trading
    path('api/tradelog/', include('tradelog.urls')),
    path('api/journal/', include('journal.urls')),

    # ── Mistakes
    path('api/mistakes/', include('mistakes.urls')),
    
    # ── Rules
    path('api/rules/', include('rules.urls')),

    # ── Discipline Guard
    path('api/discipline/', include('discipline.urls')),

    # ── Strategy Library
    path('api/strategies/', include('strategies.urls')),

    # ── Admin Panel 
    path('api/admin/', include('admin_panel.urls')),

]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)