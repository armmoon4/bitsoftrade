from django.urls import path
from .views import (
    current_session_view, session_history_view,
    unlock_session_view, violations_timeline_view
)

urlpatterns = [
    path('current-session/', current_session_view, name='discipline-current-session'),
    path('sessions/', session_history_view, name='discipline-session-history'),
    path('unlock/', unlock_session_view, name='discipline-unlock'),
    path('violations-timeline/', violations_timeline_view, name='discipline-timeline'),
]
