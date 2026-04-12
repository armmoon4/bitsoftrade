from django.urls import path, include #type: ignore
from django.conf import settings #type: ignore
from django.conf.urls.static import static #type: ignore
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView #type: ignore

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

    # ── Reports
    path('api/reports/', include('reports.urls')),

    # ── Trade intelligence report
    path('api/trade_intelligence/', include('trade_intelligence.urls')),

    # ── BitsOfTrade Insights (12 metrics)
    path('api/insights/', include('insights.urls')),
    
    # ── Learning Hub
    path('api/learninghub/', include('learninghub.urls')),

    # ── Notification
    path('api/notifications/', include('notifications.urls')),

    # ── Admin Panel 
    path('api/admin/', include('admin_panel.urls')),
    
    
    # API schema and documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    # Optional UI:
    path('api/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)