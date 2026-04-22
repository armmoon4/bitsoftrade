from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.db import transaction
from datetime import datetime, time as dtime, date as ddate, timedelta
from .models import DisciplineSession, ViolationsLog
from .serializers import DisciplineSessionSerializer, ViolationsLogSerializer


def _get_active_session(user):
    """
    Shared helper — returns the most relevant session for the given user.

    Priority:
      1. Most recent RED session within the last 30 days.
      2. Most recent YELLOW session within the last 30 days.
      3. Today's session (green fallback — created if it doesn't exist yet).

    The 30-day cutoff prevents a very old unresolved session from permanently
    blocking the user and showing stale data in the Discipline Guard.
    """
    from django.utils.timezone import localdate

    today = localdate()
    cutoff = today - timedelta(days=30)

    # 1. Most recent RED (within last 30 days)
    session = (
        DisciplineSession.objects
        .filter(user=user, session_state='red', session_date__gte=cutoff)
        .order_by('-session_date')
        .first()
    )
    if session:
        session.refresh_from_db()
        return session

    # 2. Most recent YELLOW (within last 30 days)
    session = (
        DisciplineSession.objects
        .filter(user=user, session_state='yellow', session_date__gte=cutoff)
        .order_by('-session_date')
        .first()
    )
    if session:
        session.refresh_from_db()
        return session

    # 3. Today's green session (create if missing)
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
      1. Most recent RED session (within last 30 days).
      2. Most recent YELLOW session (within last 30 days).
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
    one (within 30 days), which is exactly what the Discipline Guard card shows.

    Checklist for RED session (all 4 required):
      1. complete_journal       — user reviewed their journal
      2. complete_trade_review  — user reviewed their trades
      3. complete_all           — confirms both + starts cooldown timer (120 min)
      4. Cooldown elapsed       — passive timer, shown in UI as countdown

    Checklist for YELLOW session (2 required):
      1. complete_journal       — user reviewed their journal
      2. complete_all           — confirms + starts cooldown timer (45 min)
      3. Cooldown elapsed       — passive timer
    """
    active = _get_active_session(request.user)

    # Re-fetch with row lock inside the transaction.
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
        # Cooldown timer starts ONLY when user explicitly hits complete_all.
        # This is the 4th checklist item — it becomes a passive countdown in the UI.
        if session.cooldown_ends_at is None and session.session_state in ('yellow', 'red'):
            _COOLDOWN_YELLOW_MINUTES = 45
            _COOLDOWN_RED_MINUTES = 120
            if session.session_state == 'yellow':
                session.cooldown_ends_at = timezone.now() + timedelta(minutes=_COOLDOWN_YELLOW_MINUTES)
            elif session.session_state == 'red':
                session.cooldown_ends_at = timezone.now() + timedelta(minutes=_COOLDOWN_RED_MINUTES)
            session.save(update_fields=['cooldown_ends_at'])

    # ── Determine if unlock conditions are fully satisfied ────────────────────
    can_unlock = False
    if session.session_state == 'yellow':
        # YELLOW: only journal required
        can_unlock = session.journal_completed
    elif session.session_state == 'red':
        # RED: both journal AND trade review required
        can_unlock = session.journal_completed and session.trade_review_completed

    # ── Cooldown guard — honour DB-fresh cooldown_ends_at ────────────────────
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
        # are intentionally NOT reset — they are permanent historical record.
        session.journal_completed = False
        session.trade_review_completed = False
        try:
            from notifications.utils import create_session_notification
            create_session_notification(user=request.user, session=session, event='unlocked')
        except Exception as notif_err:
            import logging
            logging.getLogger(__name__).error(f"[Discipline] Failed to create unlock notification: {notif_err}")

    session.save()
    return Response({
        'message': 'Session unlocked.' if can_unlock else 'Action recorded. Complete required steps to unlock.',
        'session': DisciplineSessionSerializer(session).data,
    })


from datetime import date
from django.utils.dateparse import parse_date

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def violations_timeline_view(request):
    """
    GET /api/discipline/violations-timeline/?from=YYYY-MM-DD&to=YYYY-MM-DD
    Returns per-day session states in the range, including empty days.
    """
    from_date_str = request.query_params.get('from')
    to_date_str = request.query_params.get('to')

    today = date.today()
    from_date = parse_date(from_date_str) if from_date_str else today - timedelta(days=6)
    to_date = parse_date(to_date_str) if to_date_str else today

    qs = DisciplineSession.objects.filter(
        user=request.user,
        session_date__gte=from_date,
        session_date__lte=to_date,
    ).values(
        'session_date', 'session_state', 'peak_state', 'violations_count',
        'hard_violations', 'soft_violations'
    )

    sessions_by_date = {entry['session_date']: entry for entry in qs}

    timeline = []
    current = from_date
    while current <= to_date:
        if current in sessions_by_date:
            entry = sessions_by_date[current]
        else:
            entry = {
                'session_date': current,
                'session_state': None,
                'peak_state': None,
                'violations_count': 0,
                'hard_violations': 0,
                'soft_violations': 0,
            }

        timeline.append({
            **entry,
            'session_date': current.isoformat(),
            'day_label': current.strftime('%a'),
            'day_full': current.strftime('%A'),
        })
        current += timedelta(days=1)

    return Response(timeline)