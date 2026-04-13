from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import Token, UntypedToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
from rest_framework_simplejwt.settings import api_settings
from datetime import timedelta
from django.utils import timezone
from django.db.models import Q, Count, Sum, Avg
from .models import Admin, AdminUserAction, AdminAdminAction, Review, PricingPlan


class AdminRefreshToken(Token):
    """Custom refresh token for admins — no Django user_id required."""
    token_type = 'refresh'
    lifetime = api_settings.REFRESH_TOKEN_LIFETIME


class AdminAccessToken(Token):
    """Custom access token for admins — no Django user_id required."""
    token_type = 'access'
    lifetime = api_settings.ACCESS_TOKEN_LIFETIME


def get_tokens_for_admin(admin):
    """Generate JWT tokens for admin with admin_id and access_level in payload."""
    refresh = AdminRefreshToken()
    refresh['admin_id'] = str(admin.id)
    refresh['access_level'] = admin.access_level
    refresh['is_admin'] = True

    access = AdminAccessToken()
    access['admin_id'] = str(admin.id)
    access['access_level'] = admin.access_level
    access['is_admin'] = True

    return {
        'refresh': str(refresh),
        'access': str(access),
    }


class IsAdminAuthenticated(permissions.BasePermission):
    """Custom permission: validates JWT Bearer token issued to admins."""
    def has_permission(self, request, view):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return False
        raw_token = auth_header.split(' ', 1)[1]
        try:
            token = UntypedToken(raw_token)
            if not token.get('is_admin'):
                return False
            admin_id = token.get('admin_id')
            request.admin = Admin.objects.get(pk=admin_id, deleted_at__isnull=True)
            return True
        except (TokenError, InvalidToken, Admin.DoesNotExist, Exception):
            return False


# ─── Auth ─────────────────────────────────────────────────────────────────────

@api_view(['POST'])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def admin_login_view(request):
    """POST /api/admin/auth/login/"""
    email = request.data.get('email', '').strip().lower()
    password = request.data.get('password', '')

    try:
        admin = Admin.objects.get(email=email, deleted_at__isnull=True)
        if admin.check_password(password):
            tokens = get_tokens_for_admin(admin)
            return Response({
                'admin_id': str(admin.id),
                'full_name': admin.full_name,
                'email': admin.email,
                'access_level': admin.access_level,
                'tokens': tokens,
                'message': 'Login successful.'
            })
        return Response({'error': 'Invalid credentials.'}, status=status.HTTP_401_UNAUTHORIZED)
    except Admin.DoesNotExist:
        return Response({'error': 'Admin not found.'}, status=status.HTTP_401_UNAUTHORIZED)


# ─── Dashboard Stats ──────────────────────────────────────────────────────────

@api_view(['GET'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_dashboard_stats_view(request):
    """
    GET /api/admin/dashboard/stats/

    Returns a comprehensive stats payload grouped into:
      - user_growth      : totals, daily/weekly/monthly signups & growth rates
      - platform_engagement : DAU, avg session, trades/day, journal entries, strategies
      - charts           : monthly user growth trend + weekly signup breakdown
    """
    from django.contrib.auth import get_user_model
    from tradelog.models import Trade

    User = get_user_model()
    now = timezone.now()
    today = now.date()

    # ── reference windows ────────────────────────────────────────────────────
    yesterday          = today - timedelta(days=1)
    week_start         = today - timedelta(days=6)          # last 7 days incl. today
    prev_week_start    = today - timedelta(days=13)
    prev_week_end      = today - timedelta(days=7)
    month_start        = today.replace(day=1)
    prev_month_start   = (month_start - timedelta(days=1)).replace(day=1)
    prev_month_end     = month_start - timedelta(days=1)

    # ── base querysets ────────────────────────────────────────────────────────
    active_users = User.objects.filter(deleted_at__isnull=True)

    # ── USER GROWTH ──────────────────────────────────────────────────────────
    total_users       = active_users.count()
    new_today         = active_users.filter(date_joined__date=today).count()
    new_yesterday     = active_users.filter(date_joined__date=yesterday).count()
    new_this_week     = active_users.filter(date_joined__date__gte=week_start).count()
    new_prev_week     = active_users.filter(
        date_joined__date__gte=prev_week_start,
        date_joined__date__lte=prev_week_end
    ).count()
    new_this_month    = active_users.filter(date_joined__date__gte=month_start).count()
    new_prev_month    = active_users.filter(
        date_joined__date__gte=prev_month_start,
        date_joined__date__lte=prev_month_end
    ).count()

    # month-over-month growth rate  (users at end of this month vs prev month)
    users_end_prev_month = active_users.filter(date_joined__date__lte=prev_month_end).count()
    if users_end_prev_month:
        growth_rate_pct = round((new_this_month / users_end_prev_month) * 100, 1)
    else:
        growth_rate_pct = 0.0

    prev_growth_rate_pct = 0.0
    users_end_prev_prev_month = active_users.filter(date_joined__date__lt=prev_month_start).count()
    if users_end_prev_prev_month:
        prev_growth_rate_pct = round((new_prev_month / users_end_prev_prev_month) * 100, 1)

    def pct_change(current, previous):
        """Return rounded percentage change string, e.g. '+12%'."""
        if previous == 0:
            return None
        change = round(((current - previous) / previous) * 100, 1)
        return change

    def abs_change(current, previous):
        return current - previous

    user_growth = {
        'total_users': {
            'value': total_users,
            'change_pct_month': pct_change(new_this_month, new_prev_month),
        },
        'new_today': {
            'value': new_today,
            'change_vs_yesterday': abs_change(new_today, new_yesterday),
        },
        'weekly_signups': {
            'value': new_this_week,
            'change_pct_week': pct_change(new_this_week, new_prev_week),
        },
        'monthly_signups': {
            'value': new_this_month,
            'change_pct_month': pct_change(new_this_month, new_prev_month),
        },
        'growth_rate': {
            'value': growth_rate_pct,          # %
            'change_mom': round(growth_rate_pct - prev_growth_rate_pct, 1),
        },
    }

    # ── PLATFORM ENGAGEMENT ──────────────────────────────────────────────────
    try:
        from tradelog.models import Trade
        trades_today      = Trade.objects.filter(
            deleted_at__isnull=True,
            entry_date__date=today
        ).count()
        trades_per_user   = round(trades_today / total_users, 1) if total_users else 0
    except Exception:
        trades_today    = 0
        trades_per_user = 0

    try:
        from journal.models import JournalEntry
        journal_this_week = JournalEntry.objects.filter(
            deleted_at__isnull=True,
            created_at__date__gte=week_start
        ).count()
        journal_prev_week = JournalEntry.objects.filter(
            deleted_at__isnull=True,
            created_at__date__gte=prev_week_start,
            created_at__date__lte=prev_week_end
        ).count()
        journal_change_pct = pct_change(journal_this_week, journal_prev_week)
    except Exception:
        journal_this_week  = 0
        journal_change_pct = None

    try:
        from strategies.models import Strategy
        strategies_total = Strategy.objects.filter(
            deleted_at__isnull=True, is_template=False
        ).count()
    except Exception:
        strategies_total = 0

    # DAU: users who logged a trade or journal entry today
    try:
        dau = active_users.filter(
            Q(trades__entry_date__date=today) |
            Q(journal_entries__created_at__date=today)
        ).distinct().count()
    except Exception:
        dau = 0

    platform_engagement = {
        'daily_active_users': {
            'value': dau,
            'pct_of_total': round((dau / total_users * 100), 1) if total_users else 0,
        },
        # avg_session_seconds should come from your analytics/session table;
        # returning null until that model exists
        'avg_session_seconds': None,
        'trades_per_day': {
            'value': trades_today,
            'per_user_avg': trades_per_user,
        },
        'journal_entries_this_week': {
            'value': journal_this_week,
            'change_pct_week': journal_change_pct,
        },
        'strategies_created': {
            'value': strategies_total,
        },
    }

    # ── CHARTS ───────────────────────────────────────────────────────────────
    # Monthly user growth trend — last 6 months (signups per calendar month)
    monthly_trend = []
    for i in range(5, -1, -1):
        # go back i months from the current month
        ref_month_end = now.replace(day=1) - timedelta(days=1) if i > 0 else now
        ref_month_start = (now.replace(day=1) - timedelta(days=1)).replace(day=1) if i > 0 else now.replace(day=1)
        # simpler: build month offsets
        year  = now.year
        month = now.month - i
        while month <= 0:
            month += 12
            year  -= 1
        import calendar
        _, last_day = calendar.monthrange(year, month)
        ms = timezone.datetime(year, month, 1, tzinfo=now.tzinfo)
        me = timezone.datetime(year, month, last_day, 23, 59, 59, tzinfo=now.tzinfo)
        count = active_users.filter(date_joined__gte=ms, date_joined__lte=me).count()
        monthly_trend.append({
            'month': ms.strftime('%b'),
            'signups': count,
        })

    # Weekly signups — last 8 calendar weeks
    weekly_trend = []
    for i in range(7, -1, -1):
        ws = today - timedelta(days=today.weekday()) - timedelta(weeks=i)
        we = ws + timedelta(days=6)
        count = active_users.filter(
            date_joined__date__gte=ws,
            date_joined__date__lte=we
        ).count()
        weekly_trend.append({
            'week': f'W{8 - i}',
            'signups': count,
        })

    charts = {
        'monthly_user_growth': monthly_trend,
        'weekly_signups':      weekly_trend,
    }

    return Response({
        'user_growth':          user_growth,
        'platform_engagement':  platform_engagement,
        'charts':               charts,
    })


# ─── User Management ──────────────────────────────────────────────────────────

@api_view(['GET'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_user_list_view(request):
    """GET /api/admin/users/"""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    qs = User.objects.filter(deleted_at__isnull=True).order_by('-date_joined')

    sub_type = request.query_params.get('subscription_type')
    search   = request.query_params.get('search')
    if sub_type:
        qs = qs.filter(subscription_type=sub_type)
    if search:
        qs = qs.filter(Q(username__icontains=search) | Q(email__icontains=search))

    data = qs.values(
        'id', 'username', 'email', 'subscription_type',
        'subscription_status', 'is_active', 'date_joined'
    )
    return Response({'count': qs.count(), 'results': list(data)})


@api_view(['PUT'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_user_toggle_view(request, user_id):
    """PUT /api/admin/users/<id>/toggle/ — toggle is_active."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user = User.objects.filter(pk=user_id, deleted_at__isnull=True).first()
    if not user:
        return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

    prev = user.is_active
    user.is_active = not user.is_active
    user.save(update_fields=['is_active'])

    AdminUserAction.objects.create(
        admin=request.admin,
        target_user_id=user_id,
        action_type='toggle_active',
        action_detail={'from': prev, 'to': user.is_active}
    )
    return Response({'is_active': user.is_active})


@api_view(['DELETE'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_user_delete_view(request, user_id):
    """DELETE /api/admin/users/<id>/ — soft delete."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user = User.objects.filter(pk=user_id, deleted_at__isnull=True).first()
    if not user:
        return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

    user.deleted_at = timezone.now()
    user.is_active  = False
    user.save(update_fields=['deleted_at', 'is_active'])

    AdminUserAction.objects.create(
        admin=request.admin,
        target_user_id=user_id,
        action_type='delete',
        action_detail={'deleted_at': str(user.deleted_at)}
    )
    return Response(status=status.HTTP_204_NO_CONTENT)


# ─── Admin Management ─────────────────────────────────────────────────────────

@api_view(['GET'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_list_view(request):
    """GET /api/admin/admins/"""
    admins = Admin.objects.filter(deleted_at__isnull=True).values(
        'id', 'full_name', 'email', 'access_level', 'created_at'
    )
    return Response(list(admins))


@api_view(['POST'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_create_view(request):
    """POST /api/admin/admins/"""
    if request.admin.access_level != 'super_admin':
        return Response({'error': 'Only super admins can create admins.'}, status=status.HTTP_403_FORBIDDEN)

    required = ['full_name', 'email', 'password', 'access_level']
    for field in required:
        if not request.data.get(field):
            return Response({'error': f'{field} is required.'}, status=status.HTTP_400_BAD_REQUEST)

    if Admin.objects.filter(email=request.data['email']).exists():
        return Response({'error': 'Email already in use.'}, status=status.HTTP_400_BAD_REQUEST)

    new_admin = Admin(
        full_name=request.data['full_name'],
        email=request.data['email'],
        access_level=request.data['access_level'],
        created_by_admin=request.admin,
    )
    new_admin.set_password(request.data['password'])
    new_admin.save()

    AdminAdminAction.objects.create(
        performed_by_admin=request.admin,
        target_admin=new_admin,
        action_type='create',
        action_detail={'email': new_admin.email, 'access_level': new_admin.access_level}
    )
    return Response({'id': str(new_admin.id), 'email': new_admin.email}, status=status.HTTP_201_CREATED)


@api_view(['PUT', 'DELETE'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_manage_view(request, admin_id):
    """PUT/DELETE /api/admin/admins/<id>/"""
    if request.admin.access_level != 'super_admin':
        return Response({'error': 'Only super admins can manage admins.'}, status=status.HTTP_403_FORBIDDEN)

    target = Admin.objects.filter(pk=admin_id, deleted_at__isnull=True).first()
    if not target:
        return Response({'error': 'Admin not found.'}, status=status.HTTP_404_NOT_FOUND)
    if str(target.id) == str(request.admin.id):
        return Response({'error': 'Cannot modify your own account via this endpoint.'}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'PUT':
        for field in ['full_name', 'access_level']:
            if field in request.data:
                setattr(target, field, request.data[field])
        if 'password' in request.data:
            target.set_password(request.data['password'])
        target.save()
        AdminAdminAction.objects.create(
            performed_by_admin=request.admin, target_admin=target, action_type='edit',
            action_detail=request.data
        )
        return Response({'message': 'Admin updated.'})

    elif request.method == 'DELETE':
        target.deleted_at = timezone.now()
        target.save()
        AdminAdminAction.objects.create(
            performed_by_admin=request.admin, target_admin=target, action_type='delete',
            action_detail={}
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─── Rules Management ─────────────────────────────────────────────────────────

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

    elif request.method == 'POST':
        data = request.data.copy()
        rule = Rule.objects.create(
            rule_name=data.get('rule_name'),
            description=data.get('description', ''),
            category=data.get('category', 'other'),
            rule_type=data.get('rule_type', 'soft'),
            trigger_scope=data.get('trigger_scope', 'per_day'),
            trigger_condition=data.get('trigger_condition', {}),
            action=data.get('action', 'warn'),
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

    rule = Rule.objects.filter(pk=pk, is_admin_defined=True, deleted_at__isnull=True).first()
    if not rule:
        return Response({'error': 'Rule not found.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response(RuleSerializer(rule).data)

    elif request.method == 'PUT':
        for field in ['rule_name', 'description', 'category', 'rule_type',
                      'trigger_scope', 'trigger_condition', 'action', 'is_active']:
            if field in request.data:
                setattr(rule, field, request.data[field])
        rule.save()
        return Response(RuleSerializer(rule).data)

    elif request.method == 'DELETE':
        rule.deleted_at = timezone.now()
        rule.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─── Strategy Management ──────────────────────────────────────────────────────

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

    elif request.method == 'POST':
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


@api_view(['GET', 'PUT', 'DELETE'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_strategy_detail_view(request, pk):
    """GET/PUT/DELETE /api/admin/strategies/<id>/"""
    from strategies.models import Strategy
    from strategies.serializers import StrategySerializer

    strategy = Strategy.objects.filter(pk=pk, is_template=True, deleted_at__isnull=True).first()
    if not strategy:
        return Response({'error': 'Strategy not found.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response(StrategySerializer(strategy).data)

    elif request.method == 'PUT':
        for field in ['strategy_name', 'description', 'tags', 'market_types',
                      'trade_type', 'is_public', 'sample_size_threshold']:
            if field in request.data:
                setattr(strategy, field, request.data[field])
        strategy.save()
        return Response(StrategySerializer(strategy).data)

    elif request.method == 'DELETE':
        strategy.deleted_at = timezone.now()
        strategy.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─── CMS: Reviews ─────────────────────────────────────────────────────────────

def _review_to_dict(r):
    return {
        'id':            str(r.id),
        'reviewer_name': r.reviewer_name,
        'rating':        r.rating,
        'review_text':   r.review_text,
        'is_visible':    r.is_visible,
        'display_order': r.display_order,
        'created_at':    r.created_at,
        'updated_at':    r.updated_at,
    }


# ── Public ────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def public_review_list_view(request):
    """
    GET /api/cms/reviews/
    Public — returns only visible reviews, ordered by display_order.
    Used by the landing page. No auth required.
    """
    reviews = Review.objects.filter(is_visible=True)
    return Response([_review_to_dict(r) for r in reviews])


# ── Admin (protected) ─────────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_review_list_create_view(request):
    """
    GET  /api/admin/cms/reviews/   — list ALL reviews (visible + hidden) for the admin panel
    POST /api/admin/cms/reviews/   — add a new review

    POST body:
      reviewer_name  (required)
      rating         (1–5, default 5)
      review_text    (required)
      is_visible     (bool, default true)
      display_order  (int, default 0)
    """
    if request.method == 'GET':
        reviews = Review.objects.all()
        return Response([_review_to_dict(r) for r in reviews])

    elif request.method == 'POST':
        for field in ['reviewer_name', 'review_text']:
            if not request.data.get(field):
                return Response({'error': f'{field} is required.'}, status=status.HTTP_400_BAD_REQUEST)

        rating = int(request.data.get('rating', 5))
        if not (1 <= rating <= 5):
            return Response({'error': 'rating must be between 1 and 5.'}, status=status.HTTP_400_BAD_REQUEST)

        review = Review.objects.create(
            reviewer_name=request.data['reviewer_name'],
            rating=rating,
            review_text=request.data['review_text'],
            is_visible=request.data.get('is_visible', True),
            display_order=int(request.data.get('display_order', 0)),
        )
        return Response(_review_to_dict(review), status=status.HTTP_201_CREATED)


@api_view(['GET', 'PUT', 'DELETE'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_review_detail_view(request, pk):
    """
    GET    /api/admin/cms/reviews/<id>/  — retrieve
    PUT    /api/admin/cms/reviews/<id>/  — update (partial OK)
    DELETE /api/admin/cms/reviews/<id>/  — hard delete

    PUT body (all optional):
      reviewer_name, rating, review_text, is_visible, display_order
    """
    review = Review.objects.filter(pk=pk).first()
    if not review:
        return Response({'error': 'Review not found.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response(_review_to_dict(review))

    elif request.method == 'PUT':
        for field in ['reviewer_name', 'review_text', 'is_visible', 'display_order']:
            if field in request.data:
                setattr(review, field, request.data[field])
        if 'rating' in request.data:
            rating = int(request.data['rating'])
            if not (1 <= rating <= 5):
                return Response({'error': 'rating must be between 1 and 5.'}, status=status.HTTP_400_BAD_REQUEST)
            review.rating = rating
        review.save()
        return Response(_review_to_dict(review))

    elif request.method == 'DELETE':
        review.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['PATCH'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_review_toggle_visibility_view(request, pk):
    """
    PATCH /api/admin/cms/reviews/<id>/toggle-visibility/
    Toggles is_visible without a full PUT payload.
    """
    review = Review.objects.filter(pk=pk).first()
    if not review:
        return Response({'error': 'Review not found.'}, status=status.HTTP_404_NOT_FOUND)
    review.is_visible = not review.is_visible
    review.save(update_fields=['is_visible', 'updated_at'])
    return Response({'id': str(review.id), 'is_visible': review.is_visible})


# ─── CMS: Pricing Plans ───────────────────────────────────────────────────────

def _plan_to_dict(p):
    return {
        'id':            str(p.id),
        'name':          p.name,
        'price':         str(p.price),
        'billing_cycle': p.billing_cycle,
        'is_popular':    p.is_popular,
        'is_active':     p.is_active,
        'features':      p.features,
        'display_order': p.display_order,
        'created_at':    p.created_at,
        'updated_at':    p.updated_at,
    }


# ── Public ────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def public_pricing_list_view(request):
    """
    GET /api/cms/pricing/
    Public — returns only active plans, ordered by display_order.
    Used by the landing page pricing section. No auth required.
    """
    plans = PricingPlan.objects.filter(is_active=True)
    return Response([_plan_to_dict(p) for p in plans])


# ── Admin (protected) ─────────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_pricing_list_create_view(request):
    """
    GET  /api/admin/cms/pricing/   — list ALL plans (active + inactive) for the admin panel
    POST /api/admin/cms/pricing/   — create a plan

    POST body:
      name           (required)
      price          (required, decimal)
      billing_cycle  (forever|monthly|quarterly|biannual|annual)
      is_popular     (bool, default false)
      is_active      (bool, default true)
      features       (list of strings)
      display_order  (int, default 0)
    """
    if request.method == 'GET':
        plans = PricingPlan.objects.all()
        return Response([_plan_to_dict(p) for p in plans])

    elif request.method == 'POST':
        for field in ['name', 'price']:
            if request.data.get(field) is None:
                return Response({'error': f'{field} is required.'}, status=status.HTTP_400_BAD_REQUEST)

        valid_cycles = [c[0] for c in PricingPlan.BILLING_CYCLE_CHOICES]
        billing_cycle = request.data.get('billing_cycle', 'monthly')
        if billing_cycle not in valid_cycles:
            return Response({'error': f'billing_cycle must be one of {valid_cycles}.'}, status=status.HTTP_400_BAD_REQUEST)

        plan = PricingPlan.objects.create(
            name=request.data['name'],
            price=request.data['price'],
            billing_cycle=billing_cycle,
            is_popular=request.data.get('is_popular', False),
            is_active=request.data.get('is_active', True),
            features=request.data.get('features', []),
            display_order=int(request.data.get('display_order', 0)),
        )
        return Response(_plan_to_dict(plan), status=status.HTTP_201_CREATED)


@api_view(['GET', 'PUT', 'DELETE'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_pricing_detail_view(request, pk):
    """
    GET    /api/admin/cms/pricing/<id>/  — retrieve
    PUT    /api/admin/cms/pricing/<id>/  — update (partial OK)
    DELETE /api/admin/cms/pricing/<id>/  — delete

    PUT body (all optional):
      name, price, billing_cycle, is_popular, is_active, features, display_order
    """
    plan = PricingPlan.objects.filter(pk=pk).first()
    if not plan:
        return Response({'error': 'Pricing plan not found.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response(_plan_to_dict(plan))

    elif request.method == 'PUT':
        for field in ['name', 'price', 'billing_cycle', 'is_popular',
                      'is_active', 'features', 'display_order']:
            if field in request.data:
                if field == 'billing_cycle':
                    valid_cycles = [c[0] for c in PricingPlan.BILLING_CYCLE_CHOICES]
                    if request.data[field] not in valid_cycles:
                        return Response(
                            {'error': f'billing_cycle must be one of {valid_cycles}.'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                setattr(plan, field, request.data[field])
        plan.save()
        return Response(_plan_to_dict(plan))

    elif request.method == 'DELETE':
        plan.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['PATCH'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_pricing_toggle_active_view(request, pk):
    """
    PATCH /api/admin/cms/pricing/<id>/toggle-active/
    Toggles is_active on a plan.
    """
    plan = PricingPlan.objects.filter(pk=pk).first()
    if not plan:
        return Response({'error': 'Pricing plan not found.'}, status=status.HTTP_404_NOT_FOUND)
    plan.is_active = not plan.is_active
    plan.save(update_fields=['is_active', 'updated_at'])
    return Response({'id': str(plan.id), 'is_active': plan.is_active})