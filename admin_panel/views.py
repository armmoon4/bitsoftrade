"""
admin_panel/views.py
────────────────────
Thin HTTP layer.  Every view does exactly three things:
  1. Parse / validate HTTP input
  2. Call a service function
  3. Serialise and return the HTTP response

No business logic, no ORM queries, no _to_dict helpers live here.
"""

from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework import permissions, status
from rest_framework.response import Response

from mistakes.models import Mistake
from mistakes.serializers import MistakeSerializer
from .auth import IsAdminAuthenticated, get_tokens_for_admin
from .serializers import review_to_dict, plan_to_dict, broadcast_to_dict
from . import services


# ─── Auth ──────────────────────────────────────────────────────────────────────

@api_view(['POST'])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def admin_login_view(request):
    """POST /api/admin/auth/login/"""
    email    = request.data.get('email', '').strip().lower()
    password = request.data.get('password', '')

    admin = services.authenticate_admin(email, password)
    if admin is None:
        return Response({'error': 'Invalid credentials.'}, status=status.HTTP_401_UNAUTHORIZED)

    return Response({
        'admin_id':     str(admin.id),
        'full_name':    admin.full_name,
        'email':        admin.email,
        'access_level': admin.access_level,
        'tokens':       get_tokens_for_admin(admin),
        'message':      'Login successful.',
    })


# ─── Dashboard ─────────────────────────────────────────────────────────────────

@api_view(['GET'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_dashboard_stats_view(request):
    """GET /api/admin/dashboard/stats/"""
    return Response(services.get_dashboard_stats())


# ─── User Management ───────────────────────────────────────────────────────────

@api_view(['GET'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_user_list_view(request):
    """GET /api/admin/users/"""
    data = services.list_users(
        subscription_type=request.query_params.get('subscription_type'),
        search=request.query_params.get('search'),
    )
    return Response(data)


@api_view(['PUT'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_user_toggle_view(request, user_id):
    """PUT /api/admin/users/<id>/toggle/ — toggle is_active."""
    user, new_state = services.toggle_user_active(user_id, request.admin)
    if user is None:
        return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)
    return Response({'is_active': new_state})


@api_view(['DELETE'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_user_delete_view(request, user_id):
    """DELETE /api/admin/users/<id>/ — soft delete."""
    deleted = services.soft_delete_user(user_id, request.admin)
    if not deleted:
        return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)
    return Response(status=status.HTTP_204_NO_CONTENT)


# ─── Admin Management ──────────────────────────────────────────────────────────

@api_view(['GET'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_list_view(request):
    """GET /api/admin/admins/"""
    return Response(services.list_admins())


@api_view(['POST'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_create_view(request):
    """POST /api/admin/admins/"""
    if request.admin.access_level != 'super_admin':
        return Response(
            {'error': 'Only super admins can create admins.'},
            status=status.HTTP_403_FORBIDDEN,
        )
    new_admin, error = services.create_admin(request.data, request.admin)
    if error:
        return Response({'error': error}, status=status.HTTP_400_BAD_REQUEST)
    return Response({'id': str(new_admin.id), 'email': new_admin.email}, status=status.HTTP_201_CREATED)


@api_view(['PUT', 'DELETE'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_manage_view(request, admin_id):
    """PUT/DELETE /api/admin/admins/<id>/"""
    if request.admin.access_level != 'super_admin':
        return Response(
            {'error': 'Only super admins can manage admins.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.method == 'PUT':
        target, error = services.update_admin(admin_id, request.data, request.admin)
        if error == 'Admin not found.':
            return Response({'error': error}, status=status.HTTP_404_NOT_FOUND)
        if error:
            return Response({'error': error}, status=status.HTTP_403_FORBIDDEN)
        return Response({'message': 'Admin updated.'})

    elif request.method == 'DELETE':
        try:
            found = services.delete_admin(admin_id, request.admin)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_403_FORBIDDEN)
        if not found:
            return Response({'error': 'Admin not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─── Rules ─────────────────────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_rule_list_create_view(request):
    """GET/POST /api/admin/rules/"""
    from rules.models import Rule
    from rules.serializers import RuleSerializer

    if request.method == 'GET':
        rules = Rule.objects.filter(is_admin_defined=True, deleted_at__isnull=True)
        return Response(RuleSerializer(rules, many=True).data)

    rule = Rule.objects.create(
        rule_name=request.data.get('rule_name'),
        description=request.data.get('description', ''),
        category=request.data.get('category', 'other'),
        rule_type=request.data.get('rule_type', 'soft'),
        trigger_scope=request.data.get('trigger_scope', 'per_day'),
        trigger_condition=request.data.get('trigger_condition', {}),
        action=request.data.get('action', 'warn'),
        is_admin_defined=True,
        created_by_admin=request.admin,
    )
    return Response(RuleSerializer(rule).data, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PUT', 'DELETE'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_rule_detail_view(request, pk):
    """GET/PUT/DELETE /api/admin/rules/<id>/"""
    from rules.models import Rule
    from rules.serializers import RuleSerializer
    from django.utils import timezone

    rule = Rule.objects.filter(pk=pk, is_admin_defined=True, deleted_at__isnull=True).first()
    if not rule:
        return Response({'error': 'Rule not found.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response(RuleSerializer(rule).data)

    if request.method == 'PUT':
        for field in ['rule_name', 'description', 'category', 'rule_type',
                      'trigger_scope', 'trigger_condition', 'action', 'is_active']:
            if field in request.data:
                setattr(rule, field, request.data[field])
        rule.save()
        return Response(RuleSerializer(rule).data)

    rule.deleted_at = timezone.now()
    rule.save()
    return Response(status=status.HTTP_204_NO_CONTENT)


# ─── Strategies ────────────────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_strategy_list_create_view(request):
    """GET/POST /api/admin/strategies/"""
    from strategies.models import Strategy
    from strategies.serializers import StrategySerializer

    if request.method == 'GET':
        strategies = Strategy.objects.filter(
            is_template=True, deleted_at__isnull=True
        ).order_by('-created_at')
        return Response(StrategySerializer(strategies, many=True).data)

    if not request.data.get('strategy_name'):
        return Response({'error': 'strategy_name is required.'}, status=status.HTTP_400_BAD_REQUEST)

    strategy = Strategy.objects.create(
        created_by_admin=request.admin,
        user=None,
        strategy_name=request.data.get('strategy_name'),
        description=request.data.get('description', ''),
        tags=request.data.get('tags', []),
        market_types=request.data.get('market_types', []),
        trade_type=request.data.get('trade_type'),
        is_template=True,
        is_public=request.data.get('is_public', False),
        sample_size_threshold=request.data.get('sample_size_threshold', 30),
    )
    return Response(StrategySerializer(strategy).data, status=status.HTTP_201_CREATED)


# ── Mistakes (admin-defined) ──────────────────────────────────────────────────
@api_view(['GET', 'POST'])
@permission_classes([IsAdminAuthenticated])
def admin_mistake_list_create_view(request):
    if request.method == 'GET':
        mistakes = Mistake.objects.filter(is_admin_defined=True, deleted_at__isnull=True)
        data = MistakeSerializer(mistakes, many=True).data
        return Response(data)

    serializer = MistakeSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save(
            is_admin_defined=True,
            is_custom=False,
            created_by_admin=request.admin,
            user=None,
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([IsAdminAuthenticated])
def admin_mistake_detail_view(request, pk):
    try:
        mistake = Mistake.objects.get(pk=pk, is_admin_defined=True, deleted_at__isnull=True)
    except Mistake.DoesNotExist:
        return Response({'error': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response(MistakeSerializer(mistake).data)

    if request.method in ('PUT', 'PATCH'):
        serializer = MistakeSerializer(mistake, data=request.data, partial=request.method == 'PATCH')
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if request.method == 'DELETE':
        mistake.deleted_at = timezone.now()
        mistake.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET', 'PUT', 'DELETE'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_strategy_detail_view(request, pk):
    """GET/PUT/DELETE /api/admin/strategies/<id>/"""
    from strategies.models import Strategy
    from strategies.serializers import StrategySerializer
    from django.utils import timezone

    strategy = Strategy.objects.filter(pk=pk, is_template=True, deleted_at__isnull=True).first()
    if not strategy:
        return Response({'error': 'Strategy not found.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response(StrategySerializer(strategy).data)

    if request.method == 'PUT':
        for field in ['strategy_name', 'description', 'tags', 'market_types',
                      'trade_type', 'is_public', 'sample_size_threshold']:
            if field in request.data:
                setattr(strategy, field, request.data[field])
        strategy.save()
        return Response(StrategySerializer(strategy).data)

    strategy.deleted_at = timezone.now()
    strategy.save()
    return Response(status=status.HTTP_204_NO_CONTENT)


# ─── CMS: Reviews — Public ─────────────────────────────────────────────────────

@api_view(['GET'])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def public_review_list_view(request):
    """GET /api/cms/reviews/"""
    from .models import Review
    reviews = Review.objects.filter(is_visible=True)
    return Response([review_to_dict(r) for r in reviews])


# ─── CMS: Reviews — Admin ──────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_review_list_create_view(request):
    """GET/POST /api/admin/cms/reviews/"""
    from .models import Review

    if request.method == 'GET':
        return Response([review_to_dict(r) for r in Review.objects.all()])

    review, error = services.create_review(request.data)
    if error:
        return Response({'error': error}, status=status.HTTP_400_BAD_REQUEST)
    return Response(review_to_dict(review), status=status.HTTP_201_CREATED)


@api_view(['GET', 'PUT', 'DELETE'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_review_detail_view(request, pk):
    """GET/PUT/DELETE /api/admin/cms/reviews/<id>/"""
    from .models import Review

    review = Review.objects.filter(pk=pk).first()
    if not review:
        return Response({'error': 'Review not found.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response(review_to_dict(review))

    if request.method == 'PUT':
        review, error = services.update_review(review, request.data)
        if error:
            return Response({'error': error}, status=status.HTTP_400_BAD_REQUEST)
        return Response(review_to_dict(review))

    review.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['PATCH'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_review_toggle_visibility_view(request, pk):
    """PATCH /api/admin/cms/reviews/<id>/toggle-visibility/"""
    from .models import Review

    review = Review.objects.filter(pk=pk).first()
    if not review:
        return Response({'error': 'Review not found.'}, status=status.HTTP_404_NOT_FOUND)
    review = services.toggle_review_visibility(review)
    return Response({'id': str(review.id), 'is_visible': review.is_visible})


# ─── CMS: Pricing Plans — Public ───────────────────────────────────────────────

@api_view(['GET'])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def public_pricing_list_view(request):
    """GET /api/cms/pricing/"""
    from .models import PricingPlan
    plans = PricingPlan.objects.filter(is_active=True)
    return Response([plan_to_dict(p) for p in plans])


# ─── CMS: Pricing Plans — Admin ────────────────────────────────────────────────

@api_view(['GET', 'POST'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_pricing_list_create_view(request):
    """GET/POST /api/admin/cms/pricing/"""
    from .models import PricingPlan

    if request.method == 'GET':
        return Response([plan_to_dict(p) for p in PricingPlan.objects.all()])

    plan, error = services.create_pricing_plan(request.data)
    if error:
        return Response({'error': error}, status=status.HTTP_400_BAD_REQUEST)
    return Response(plan_to_dict(plan), status=status.HTTP_201_CREATED)


@api_view(['GET', 'PUT', 'DELETE'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_pricing_detail_view(request, pk):
    """GET/PUT/DELETE /api/admin/cms/pricing/<id>/"""
    from .models import PricingPlan

    plan = PricingPlan.objects.filter(pk=pk).first()
    if not plan:
        return Response({'error': 'Pricing plan not found.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response(plan_to_dict(plan))

    if request.method == 'PUT':
        plan, error = services.update_pricing_plan(plan, request.data)
        if error:
            return Response({'error': error}, status=status.HTTP_400_BAD_REQUEST)
        return Response(plan_to_dict(plan))

    plan.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['PATCH'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_pricing_toggle_active_view(request, pk):
    """PATCH /api/admin/cms/pricing/<id>/toggle-active/"""
    from .models import PricingPlan

    plan = PricingPlan.objects.filter(pk=pk).first()
    if not plan:
        return Response({'error': 'Pricing plan not found.'}, status=status.HTTP_404_NOT_FOUND)
    plan = services.toggle_plan_active(plan)
    return Response({'id': str(plan.id), 'is_active': plan.is_active})


# ─── Broadcast Notifications ───────────────────────────────────────────────────

@api_view(['GET', 'POST'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_broadcast_list_create_view(request):
    """GET/POST /api/admin/notifications/broadcasts/"""
    from notifications.models import AdminBroadcast

    if request.method == 'GET':
        broadcasts = AdminBroadcast.objects.select_related('sent_by_admin').all()
        return Response([broadcast_to_dict(b) for b in broadcasts])

    title      = request.data.get('title', '').strip()
    message    = request.data.get('message', '').strip()
    recipients = request.data.get('recipients', '').strip()

    if not title:
        return Response({'error': 'title is required.'}, status=status.HTTP_400_BAD_REQUEST)
    if not message:
        return Response({'error': 'message is required.'}, status=status.HTTP_400_BAD_REQUEST)

    broadcast, error = services.send_broadcast(title, message, recipients, request.admin)
    if error:
        return Response({'error': error}, status=status.HTTP_400_BAD_REQUEST)
    return Response(broadcast_to_dict(broadcast), status=status.HTTP_201_CREATED)


@api_view(['DELETE'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_broadcast_delete_view(request, pk):
    """DELETE /api/admin/notifications/broadcasts/<id>/"""
    from notifications.models import AdminBroadcast

    broadcast = AdminBroadcast.objects.filter(pk=pk).first()
    if not broadcast:
        return Response({'error': 'Broadcast not found.'}, status=status.HTTP_404_NOT_FOUND)
    broadcast.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)