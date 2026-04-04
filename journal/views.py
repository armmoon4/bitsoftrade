from rest_framework import generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta
from discipline.views import _get_active_session
from .models import DailyJournal, TradeNote, PsychologyLog, SessionRecap, LearningNote
from .serializers import (
    DailyJournalSerializer, TradeNoteSerializer,
    PsychologyLogSerializer, SessionRecapSerializer, LearningNoteSerializer
)
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

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['active_session'] = _get_active_session(self.request.user)
        return context

    #_______________DUPLICATEDATEVAL___________________
    # def perform_create(self, serializer):
    #     # 1. Get the date from the validated request data
    #     journal_date = serializer.validated_data.get('journal_date')

    #     # 2. Check if a journal entry already exists for this user and date
    #     if journal_date and DailyJournal.objects.filter(user=self.request.user, journal_date=journal_date).exists():
    #         raise ValidationError({
    #             "journal_date": ["A daily journal entry for this date already exists. Please update the existing entry instead."]
    #         })

    #     # 3. If it doesn't exist, proceed with creation using the base class method
    #     super().perform_create(serializer)
    #_______________DUPLICATEDATEVAL___________________

class DailyJournalDetailView(BaseJournalDetailView):
    queryset = DailyJournal.objects.all()
    serializer_class = DailyJournalSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['active_session'] = _get_active_session(self.request.user)
        return context


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


# --- Journal Streak View ---
class JournalStreakAPIView(APIView):
    """
    Returns the user's current consecutive journaling streak
    and the list of active journal dates for the current month.

    Uses DailyJournal.journal_date as the activity source —
    no separate UserActivity model needed.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        today = timezone.now().date()

        # --- 1. CALCULATE CONSECUTIVE STREAK ---
        # Fetch all journal dates up to today into a Set for O(1) lookups
        all_journal_dates = set(
            DailyJournal.objects.filter(
                user=user,
                journal_date__lte=today
            ).values_list('journal_date', flat=True)
        )

        streak = 0
        check_date = today

        # Grace: if user hasn't journaled today yet, start counting from yesterday
        # so we don't reset an active streak prematurely
        if check_date not in all_journal_dates:
            check_date -= timedelta(days=1)

        # Walk backwards until the streak breaks
        while check_date in all_journal_dates:
            streak += 1
            check_date -= timedelta(days=1)

        # --- 2. GET THIS MONTH'S ACTIVE DATES ---
        start_of_month = today.replace(day=1)

        month_dates = DailyJournal.objects.filter(
            user=user,
            journal_date__gte=start_of_month,
            journal_date__lte=today,
        ).values_list('journal_date', flat=True)

        active_this_month = [d.strftime('%Y-%m-%d') for d in month_dates]

        return Response({
            "current_streak": streak,
            "this_month_active_dates": active_this_month,
        })