from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.db import transaction
from datetime import datetime, time as dtime, date as ddate, timedelta, date
from .models import DisciplineSession, ViolationsLog
from .serializers import DisciplineSessionSerializer, ViolationsLogSerializer


def _get_active_session(user):
    """
    Returns the most relevant session for the Discipline Guard UI.

    Uses the same get_active_locked_session() from rules.engine so that
    the discipline guard, import block, and add-trade block all show and
    act on the EXACT same session — there is no inconsistency.

    Priority:
      1. Most recent RED session within 30 days  → user must complete checklist
      2. Most recent YELLOW session within 30 days → user must complete journal
      3. Today's green session (created if missing) → everything is fine
    """
    from rules.engine import get_active_locked_session
    from django.utils.timezone import localdate

    # Use the shared engine helper — single source of truth
    locked_session = get_active_locked_session(user)
    if locked_session:
        locked_session.refresh_from_db()
        return locked_session

    # No locked session — return or create today's green session
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

    Returns the active session for the Discipline Guard card:
      1. Most recent RED session (within 30 days) — must unlock
      2. Most recent YELLOW session (within 30 days) — must complete journal
      3. Today's green session — all clear
    """
    session = _get_active_session(request.user)
    return Response(DisciplineSessionSerializer(session).data)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def session_history_view(request):
    """GET /api/discipline/sessions/ — Full session history."""
    sessions = DisciplineSession.objects.filter(user=request.user).order_by('-session_date')
    return Response(DisciplineSessionSerializer(sessions, many=True).data)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@transaction.atomic
def unlock_session_view(request):
    """
    POST /api/discipline/unlock/
    Body: { "action": "complete_journal" | "complete_trade_review" | "complete_all" }

    Works on the same session that current_session_view shows — no date needed.

    Checklist for RED session (all required before unlock):
      1. complete_journal       — user reviewed journal entry
      2. complete_trade_review  — user reviewed their trades
      3. complete_all           — confirms both items + starts cooldown timer
      4. Cooldown elapsed       — passive countdown shown in UI (120 min for RED)

    Checklist for YELLOW session:
      1. complete_journal       — user reviewed journal entry
      2. complete_all           — confirms + starts cooldown timer (45 min for YELLOW)
      3. Cooldown elapsed       — passive countdown shown in UI
    """
    active = _get_active_session(request.user)

    # Re-fetch with row lock inside the transaction
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
        # Cooldown starts ONLY when user explicitly clicks complete_all.
        # This is the 4th checklist item — rendered as a countdown timer in UI.
        if session.cooldown_ends_at is None and session.session_state in ('yellow', 'red'):
            _COOLDOWN_YELLOW_MINUTES = 5
            _COOLDOWN_RED_MINUTES = 1
            if session.session_state == 'yellow':
                session.cooldown_ends_at = timezone.now() + timedelta(minutes=_COOLDOWN_YELLOW_MINUTES)
            elif session.session_state == 'red':
                session.cooldown_ends_at = timezone.now() + timedelta(minutes=_COOLDOWN_RED_MINUTES)
            session.save(update_fields=['cooldown_ends_at'])

    # ── Check whether all unlock conditions are met ───────────────────────────
    can_unlock = False
    if session.session_state == 'yellow':
        can_unlock = session.journal_completed
    elif session.session_state == 'red':
        can_unlock = session.journal_completed and session.trade_review_completed

    # ── Cooldown guard ────────────────────────────────────────────────────────
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
        # Historical violation counts intentionally kept — never reset on unlock
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