from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from . import views

urlpatterns = [
    # Core Auth
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # JWT Standard endpoints
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Profile Management
    path('me/', views.current_user_view, name='current_user'),
    path('profile/', views.profile_view, name='profile'),
    
    # Password Management
    path('password/change/', views.change_password_view, name='change_password'),
    path('password/reset/', views.request_password_reset, name='request_password_reset'),
    path('password/reset/confirm/', views.confirm_password_reset, name='confirm_password_reset'),
    
    # Google Auth
    path('google-login/', views.google_login_view, name='google_login'),
]