from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.db import transaction
from datetime import datetime, time as dtime, date as ddate, timedelta, date
from .models import DisciplineSession, ViolationsLog
from .serializers import DisciplineSessionSerializer, ViolationsLogSerializer
from accounts.permissions import HasToolSubscription


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


def _all_flagged_trades_tagged(session):
    """
    Gate check — returns True only when EVERY trade that has a ViolationsLog
    entry for this session has at least one TradeMistake row linked to it.

    A trade is considered "mistakes tagged" when the user has explicitly
    selected at least one mistake from the Mistakes panel on that trade
    (i.e. a TradeMistake junction row exists for it).

    Vacuously True when the session has no flagged trades at all.
    """
    from mistakes.models import TradeMistake

    flagged_ids = list(
        session.violation_logs
        .filter(trade__isnull=False)
        .values_list('trade_id', flat=True)
        .distinct()
    )

    if not flagged_ids:
        return True  # No violations logged — gate passes automatically

    # Trades that have at least one TradeMistake entry
    trades_with_mistake = set(
        TradeMistake.objects
        .filter(trade_id__in=flagged_ids)
        .values_list('trade_id', flat=True)
        .distinct()
    )

    # Every flagged trade must have a mistake tagged
    return set(flagged_ids) == trades_with_mistake


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, HasToolSubscription])
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
@permission_classes([permissions.IsAuthenticated, HasToolSubscription])
def session_history_view(request):
    """GET /api/discipline/sessions/ — Full session history."""
    sessions = DisciplineSession.objects.filter(user=request.user).order_by('-session_date')
    return Response(DisciplineSessionSerializer(sessions, many=True).data)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated, HasToolSubscription])
@transaction.atomic
def unlock_session_view(request):
    active = _get_active_session(request.user)
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

    # ── Cooldown guard ────────────────────────────────────────────────────
    # Cooldown is started automatically by the rule engine when the session
    # first escalates. Here we only CHECK whether it has elapsed.
    all_tagged = _all_flagged_trades_tagged(session)

    if session.cooldown_ends_at:
        now = timezone.now()
        if now < session.cooldown_ends_at:
            remaining_minutes = max(1, int((session.cooldown_ends_at - now).total_seconds() // 60))
            session.save(update_fields=['journal_completed', 'trade_review_completed'])
            return Response({
                'message': f'Cooldown active. {remaining_minutes} minute(s) remaining.',
                'cooldown_ends_at': session.cooldown_ends_at,
                'all_trades_tagged': all_tagged,
                'session': DisciplineSessionSerializer(session).data,
            }, status=status.HTTP_202_ACCEPTED)

    # ── Check whether all unlock conditions are met ───────────────────────
    # `all_tagged` is the gate: every trade flagged in ViolationsLog must
    # have is_tagged_complete=True before we allow the session to go GREEN.
    can_unlock = False
    if session.session_state == 'yellow':
        can_unlock = session.journal_completed and all_tagged
    elif session.session_state == 'red':
        can_unlock = session.journal_completed and session.trade_review_completed and all_tagged

    if can_unlock:
        now_ts = timezone.now()
        session.session_state = 'green'
        session.required_actions_completed = True
        session.unlocked_at = now_ts
        session.lock_cycle = (session.lock_cycle or 0) + 1
        session.lock_cycle_started_at = now_ts
        session.cooldown_ends_at = None
        session.journal_completed = False
        session.trade_review_completed = False
        session.save()

        DisciplineSession.objects.filter(
            user=request.user,
            session_state__in=['red', 'yellow'],
        ).exclude(pk=session.pk).update(
            session_state='green',
            required_actions_completed=True,
            unlocked_at=now_ts,
            cooldown_ends_at=None,
            journal_completed=False,
            trade_review_completed=False,
        )

        try:
            from notifications.utils import create_session_notification
            create_session_notification(user=request.user, session=session, event='unlocked')
        except Exception as notif_err:
            import logging
            logging.getLogger(__name__).error(f"[Discipline] Failed to create unlock notification: {notif_err}")

        return Response({
            'message': 'Session unlocked.',
            'session': DisciplineSessionSerializer(session).data,
        })

    # Checklist item recorded but not yet ready to unlock
    session.save()
    return Response({
        'message': 'Action recorded. Complete required steps to unlock.',
        'all_trades_tagged': all_tagged,
        'session': DisciplineSessionSerializer(session).data,
    })


from django.utils.dateparse import parse_date

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, HasToolSubscription])
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