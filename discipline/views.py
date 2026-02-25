from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.utils import timezone
from django.shortcuts import get_object_or_404
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
def unlock_session_view(request):
    """
    POST /api/discipline/unlock/
    Body: { action: 'complete_journal' | 'complete_trade_review' | 'complete_all' }
    Attempts to unlock a YELLOW or RED session.
    """
    from django.utils.timezone import localdate
    today = localdate()
    session = get_object_or_404(DisciplineSession, user=request.user, session_date=today)

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

    # Check cooldown
    if can_unlock and session.cooldown_ends_at:
        if timezone.now() < session.cooldown_ends_at:
            remaining = (session.cooldown_ends_at - timezone.now()).seconds // 60
            session.save()
            return Response({
                'message': f'Cooldown active. {remaining} minutes remaining.',
                'session': DisciplineSessionSerializer(session).data
            }, status=status.HTTP_202_ACCEPTED)

    if can_unlock:
        session.session_state = 'green'
        session.required_actions_completed = True
        session.unlocked_at = timezone.now()

    session.save()
    return Response({
        'message': 'Session unlocked.' if can_unlock else 'Action recorded. Complete required steps to unlock.',
        'session': DisciplineSessionSerializer(session).data
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
