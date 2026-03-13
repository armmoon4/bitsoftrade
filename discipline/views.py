from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.db import transaction
from datetime import datetime, time as dtime, date as ddate
from .models import DisciplineSession, ViolationsLog
from .serializers import DisciplineSessionSerializer, ViolationsLogSerializer


def _get_active_session(user):
    """
    Shared helper — returns the most relevant session for the given user.

    Priority:
      1. Most recent RED session (fully locked until actions completed).
      2. Most recent YELLOW session (cooldown or awaiting journal).
      3. Today's session (green fallback — created if it doesn't exist yet).

    Both current_session_view and unlock_session_view use this so they
    always operate on the exact same session — no date param needed.
    """
    from django.utils.timezone import localdate

    # 1. Most recent RED
    session = (
        DisciplineSession.objects
        .filter(user=user, session_state='red')
        .order_by('-session_date')
        .first()
    )
    if session:
        session.refresh_from_db()
        return session

    # 2. Most recent YELLOW
    session = (
        DisciplineSession.objects
        .filter(user=user, session_state='yellow')
        .order_by('-session_date')
        .first()
    )
    if session:
        session.refresh_from_db()
        return session

    # 3. Today's green session (create if missing)
    today = localdate()
    session, created = DisciplineSession.objects.get_or_create(
        user=user,
        session_date=today,
        defaults={'session_state': 'green'},
    )
    if created or session.lock_cycle_started_at is None:
        day_start = timezone.make_aware(datetime.combine(today, dtime.min))
        session.lock_cycle_started_at = day_start
        session.save(update_fields=['lock_cycle_started_at'])

    session.refresh_from_db()
    return session


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def current_session_view(request):
    """
    GET /api/discipline/current-session/

    Returns the most relevant session for the Discipline Guard UI:
      1. Most recent RED session (past or today).
      2. Most recent YELLOW session (past or today).
      3. Today's green session as fallback.
    """
    session = _get_active_session(request.user)
    return Response(DisciplineSessionSerializer(session).data)


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

    Unlocks the same session that current_session_view returns — no date
    param needed. The active session is always the most recent RED/YELLOW
    one, which is exactly what the Discipline Guard card is showing.
    """
    # Resolve which session is currently active — same logic as current_session_view.
    # select_for_update() requires a transaction (provided by @transaction.atomic).
    active = _get_active_session(request.user)

    # Re-fetch with row lock now that we know the PK.
    session = (
        DisciplineSession.objects
        .select_for_update()
        .get(pk=active.pk)
    )

    action = request.data.get('action', '')

    if action == 'complete_journal':
        session.journal_completed = True
    elif action == 'complete_trade_review':
        session.trade_review_completed = True
    elif action == 'complete_all':
        session.journal_completed = True
        session.trade_review_completed = True
        # Cooldown starts ONLY when user hits complete_all — not before.
        # This means the timer begins the moment the user confirms both
        # checklist items, not when the session first locked.
        if session.cooldown_ends_at is None and session.session_state in ('yellow', 'red'):
            from datetime import timedelta
            _COOLDOWN_YELLOW_MINUTES = 45
            _COOLDOWN_RED_MINUTES = 120
            if session.session_state == 'yellow':
                session.cooldown_ends_at = timezone.now() + timedelta(minutes=_COOLDOWN_YELLOW_MINUTES)
            elif session.session_state == 'red':
                session.cooldown_ends_at = timezone.now() + timedelta(minutes=_COOLDOWN_RED_MINUTES)
            session.save(update_fields=['cooldown_ends_at'])

    # Determine whether unlock conditions are satisfied
    can_unlock = False
    if session.session_state == 'yellow':
        can_unlock = session.journal_completed
    elif session.session_state == 'red':
        can_unlock = session.journal_completed and session.trade_review_completed

    # Cooldown guard — honour DB-fresh cooldown_ends_at
    if can_unlock and session.cooldown_ends_at:
        now = timezone.now()
        if now < session.cooldown_ends_at:
            remaining_minutes = max(1, int((session.cooldown_ends_at - now).total_seconds() // 60))
            session.save(update_fields=['journal_completed', 'trade_review_completed'])
            return Response({
                'message': f'Cooldown active. {remaining_minutes} minute(s) remaining.',
                'cooldown_ends_at': session.cooldown_ends_at,
                'session': DisciplineSessionSerializer(session).data,
            }, status=status.HTTP_202_ACCEPTED)

    if can_unlock:
        session.session_state = 'green'
        session.required_actions_completed = True
        session.unlocked_at = timezone.now()
        session.lock_cycle = (session.lock_cycle or 0) + 1
        session.lock_cycle_started_at = timezone.now()
        session.cooldown_ends_at = None
        # NOTE: rules_violated, violations_count, hard_violations, soft_violations
        # are intentionally NOT reset here — they are permanent historical record
        # for this session date and power the behavior metrics.
        # Only the cycle-control and UI-state fields are reset.
        session.journal_completed = False
        session.trade_review_completed = False

    session.save()
    return Response({
        'message': 'Session unlocked.' if can_unlock else 'Action recorded. Complete required steps to unlock.',
        'session': DisciplineSessionSerializer(session).data,
    })

from datetime import date, timedelta

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def violations_timeline_view(request):
    """
    GET /api/discipline/violations-timeline/

    Anchors to the most recent week that had ANY violation.
    Falls back to most recent session week if no violations exist.
    Returns all 7 days Mon–Sun of that week, gap-filled with green/0.
    """
    # Anchor to most recent session that had at least 1 violation
    latest = (
        DisciplineSession.objects
        .filter(user=request.user, violations_count__gt=0)
        .order_by('-session_date')
        .first()
    )

    # Fallback: most recent session of any kind
    if not latest:
        latest = (
            DisciplineSession.objects
            .filter(user=request.user)
            .order_by('-session_date')
            .first()
        )

    # Last fallback: no sessions at all
    anchor = latest.session_date if latest else ddate.today()

    # Mon–Sun week containing the anchor date
    week_start = anchor - timedelta(days=anchor.weekday())
    week_end   = week_start + timedelta(days=6)

    sessions_qs = (
        DisciplineSession.objects
        .filter(user=request.user, session_date__gte=week_start, session_date__lte=week_end)
        .values('session_date', 'session_state', 'violations_count',
                'hard_violations', 'soft_violations')
    )
    sessions_by_date = {row['session_date']: row for row in sessions_qs}

    _STATE_LABEL = {'green': 'Normal', 'yellow': 'Caution', 'red': 'Restricted'}

    timeline = []
    for i in range(7):
        day = week_start + timedelta(days=i)
        row = sessions_by_date.get(day, {
            'session_date':     day,
            'session_state':    'green',
            'violations_count': 0,
            'hard_violations':  0,
            'soft_violations':  0,
        })
        timeline.append({
            **row,
            'label': _STATE_LABEL.get(row['session_state'], 'Normal'),
        })

    return Response(timeline)