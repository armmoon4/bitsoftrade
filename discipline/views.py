from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.db import transaction
from datetime import datetime, time as dtime
from .models import DisciplineSession, ViolationsLog
from .serializers import DisciplineSessionSerializer, ViolationsLogSerializer


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def current_session_view(request):
    """GET /api/discipline/current-session/ — Today's session state."""
    from django.utils.timezone import localdate
    today = localdate()
    session, created = DisciplineSession.objects.get_or_create(
        user=request.user,
        session_date=today,
        defaults={'session_state': 'green'}
    )
    # Initialise lock_cycle_started_at for brand-new sessions (or old ones
    # that were created before this field existed). Use start-of-day so ALL
    # trades saved that day are included in the cycle count from trade #1.
    if created or session.lock_cycle_started_at is None:
        day_start = timezone.make_aware(
            datetime.combine(today, dtime.min)
        )
        session.lock_cycle_started_at = day_start
        session.save(update_fields=['lock_cycle_started_at'])
    serializer = DisciplineSessionSerializer(session)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def session_history_view(request):
    """GET /api/discipline/sessions/ — Full session history."""
    sessions = DisciplineSession.objects.filter(user=request.user).order_by('-session_date')
    serializer = DisciplineSessionSerializer(sessions, many=True)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@transaction.atomic
def unlock_session_view(request):
    """
    POST /api/discipline/unlock/
    Body: { action: 'complete_journal' | 'complete_trade_review' | 'complete_all' }
    Attempts to unlock a YELLOW or RED session.
    """
    from django.utils.timezone import localdate
    today = localdate()

    # Always re-fetch the session fresh from the DB before any checks.
    # select_for_update() requires @transaction.atomic (added above) — this
    # locks the row for the duration of this request so no concurrent unlock
    # can race and cause a stale cooldown_ends_at to be used.
    session = get_object_or_404(
        DisciplineSession.objects.select_for_update(),
        user=request.user,
        session_date=today,
    )

    action = request.data.get('action', '')

    if action == 'complete_journal':
        session.journal_completed = True
    elif action == 'complete_trade_review':
        session.trade_review_completed = True
    elif action == 'complete_all':
        session.journal_completed = True
        session.trade_review_completed = True

    # Check if unlock conditions are met
    can_unlock = False
    if session.session_state == 'yellow':
        can_unlock = session.journal_completed
    elif session.session_state == 'red':
        can_unlock = session.journal_completed and session.trade_review_completed

    # ── FIX: Cooldown guard — always check against the DB-fresh cooldown_ends_at.
    # On cycle 2+ the engine writes a new cooldown_ends_at when it re-locks the
    # session. We must honour that new value, not a stale one from a prior cycle.
    if can_unlock and session.cooldown_ends_at:
        now = timezone.now()
        if now < session.cooldown_ends_at:
            remaining_seconds = (session.cooldown_ends_at - now).total_seconds()
            remaining_minutes = max(1, int(remaining_seconds // 60))
            # Save the journal/review progress but do NOT unlock yet.
            session.save(update_fields=[
                'journal_completed',
                'trade_review_completed',
            ])
            return Response({
                'message': f'Cooldown active. {remaining_minutes} minute(s) remaining.',
                'cooldown_ends_at': session.cooldown_ends_at,
                'session': DisciplineSessionSerializer(session).data,
            }, status=status.HTTP_202_ACCEPTED)

    if can_unlock:
        session.session_state = 'green'
        # peak_state is intentionally NOT reset — it preserves the historical record
        # of the highest severity reached, used by all 12 behavior metrics.
        session.required_actions_completed = True
        session.unlocked_at = timezone.now()

        # Increment lock_cycle so the rule engine treats the next violation
        # check as a fresh cycle. This allows the same rule to re-trigger and
        # re-lock the session if the user repeats a violation.
        session.lock_cycle = (session.lock_cycle or 0) + 1

        # Record when this new cycle started so the rule engine counts only
        # trades created from this point forward (fresh quota per cycle).
        session.lock_cycle_started_at = timezone.now()

        # ── FIX: Clear cooldown_ends_at on unlock so that stale timestamps
        # from this cycle can never accidentally pass the cooldown guard in
        # a future cycle. The engine will set a fresh value if re-locked.
        session.cooldown_ends_at = None

        # Reset per-cycle counters so they correctly reflect violations
        # accumulated since this unlock (not across the entire day).
        session.rules_violated = []
        session.violations_count = 0
        session.hard_violations = 0
        session.soft_violations = 0

        # Reset journal / review flags for the new lock cycle so the user
        # must complete them again if they get locked again today.
        session.journal_completed = False
        session.trade_review_completed = False

    session.save()
    return Response({
        'message': 'Session unlocked.' if can_unlock else 'Action recorded. Complete required steps to unlock.',
        'session': DisciplineSessionSerializer(session).data,
    })


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def violations_timeline_view(request):
    """
    GET /api/discipline/violations-timeline/?from=YYYY-MM-DD&to=YYYY-MM-DD
    Returns per-day session states in the range.
    """
    from_date = request.query_params.get('from')
    to_date = request.query_params.get('to')

    qs = DisciplineSession.objects.filter(user=request.user)
    if from_date:
        qs = qs.filter(session_date__gte=from_date)
    if to_date:
        qs = qs.filter(session_date__lte=to_date)

    timeline = qs.values('session_date', 'session_state', 'violations_count',
                         'hard_violations', 'soft_violations').order_by('session_date')
    return Response(list(timeline))