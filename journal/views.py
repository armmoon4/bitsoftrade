from rest_framework import generics, permissions
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from .models import DailyJournal, TradeNote, PsychologyLog, SessionRecap, LearningNote
from .serializers import (
    DailyJournalSerializer, TradeNoteSerializer, 
    PsychologyLogSerializer, SessionRecapSerializer, LearningNoteSerializer
)
# Assuming you have a core pagination file or you can import from tradelog
from tradelog.pagination import StandardResultsSetPagination 

class BaseJournalListCreateView(generics.ListCreateAPIView):
    """Base view to handle common List/Create logic for all journal models."""
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class BaseJournalDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Base view to handle common Detail logic for all journal models."""
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)


# --- Daily Journal Views ---
class DailyJournalListCreateView(BaseJournalListCreateView):
    queryset = DailyJournal.objects.all()
    serializer_class = DailyJournalSerializer

    def perform_create(self, serializer):
        journal_date = serializer.validated_data.get('journal_date')
        if DailyJournal.objects.filter(user=self.request.user, journal_date=journal_date).exists():
            raise ValidationError({
                "journal_date": "You have already created a journal entry for this date."
            })
        serializer.save(user=self.request.user)

class DailyJournalDetailView(BaseJournalDetailView):
    queryset = DailyJournal.objects.all()
    serializer_class = DailyJournalSerializer


# --- Trade Notes Views ---
class TradeNoteListCreateView(BaseJournalListCreateView):
    queryset = TradeNote.objects.all()
    serializer_class = TradeNoteSerializer

class TradeNoteDetailView(BaseJournalDetailView):
    queryset = TradeNote.objects.all()
    serializer_class = TradeNoteSerializer


# --- Psychology Log Views ---
class PsychologyLogListCreateView(BaseJournalListCreateView):
    queryset = PsychologyLog.objects.all()
    serializer_class = PsychologyLogSerializer

class PsychologyLogDetailView(BaseJournalDetailView):
    queryset = PsychologyLog.objects.all()
    serializer_class = PsychologyLogSerializer


# --- Session Recap Views ---
class SessionRecapListCreateView(BaseJournalListCreateView):
    queryset = SessionRecap.objects.all()
    serializer_class = SessionRecapSerializer

class SessionRecapDetailView(BaseJournalDetailView):
    queryset = SessionRecap.objects.all()
    serializer_class = SessionRecapSerializer


# --- Learning Notes Views ---
class LearningNoteListCreateView(BaseJournalListCreateView):
    queryset = LearningNote.objects.all()
    serializer_class = LearningNoteSerializer

class LearningNoteDetailView(BaseJournalDetailView):
    queryset = LearningNote.objects.all()
    serializer_class = LearningNoteSerializer