from django.urls import path
from .views import (
    DailyJournalListCreateView, DailyJournalDetailView,
    TradeNoteListCreateView, TradeNoteDetailView,
    PsychologyLogListCreateView, PsychologyLogDetailView,
    SessionRecapListCreateView, SessionRecapDetailView,
    LearningNoteListCreateView, LearningNoteDetailView
)

urlpatterns = [
    # Daily Journals
    path('daily/', DailyJournalListCreateView.as_view(), name='journal-daily-list'),
    path('daily/<uuid:pk>/', DailyJournalDetailView.as_view(), name='journal-daily-detail'),
    
    # Trade Notes
    path('trade-notes/', TradeNoteListCreateView.as_view(), name='journal-tradenote-list'),
    path('trade-notes/<uuid:pk>/', TradeNoteDetailView.as_view(), name='journal-tradenote-detail'),
    
    # Psychology Logs
    path('psychology/', PsychologyLogListCreateView.as_view(), name='journal-psych-list'),
    path('psychology/<uuid:pk>/', PsychologyLogDetailView.as_view(), name='journal-psych-detail'),
    
    # Session Recaps
    path('recaps/', SessionRecapListCreateView.as_view(), name='journal-recap-list'),
    path('recaps/<uuid:pk>/', SessionRecapDetailView.as_view(), name='journal-recap-detail'),
    
    # Learning Notes
    path('learning-notes/', LearningNoteListCreateView.as_view(), name='journal-learningnote-list'),
    path('learning-notes/<uuid:pk>/', LearningNoteDetailView.as_view(), name='journal-learningnote-detail'),
]