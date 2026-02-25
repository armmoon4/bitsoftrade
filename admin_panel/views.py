from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import Token, UntypedToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
from rest_framework_simplejwt.settings import api_settings
from datetime import timedelta
from django.utils import timezone
from django.db.models import Q, Count, Sum
from .models import Admin, AdminUserAction, AdminAdminAction


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
            # UntypedToken validates signature & expiry without requiring user_id
            token = UntypedToken(raw_token)
            if not token.get('is_admin'):
                return False
            admin_id = token.get('admin_id')
            request.admin = Admin.objects.get(pk=admin_id, deleted_at__isnull=True)
            return True
        except (TokenError, InvalidToken, Admin.DoesNotExist, Exception):
            return False


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


@api_view(['GET'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_dashboard_stats_view(request):
    """GET /api/admin/dashboard/stats/"""
    from django.contrib.auth import get_user_model
    from tradelog.models import Trade

    User = get_user_model()
    today = timezone.now().date()

    stats = {
        'total_users': User.objects.filter(deleted_at__isnull=True).count(),
        'todays_new_users': User.objects.filter(date_joined__date=today).count(),
        'total_subscribers': User.objects.filter(
            subscription_status='active'
        ).exclude(subscription_type='none').count(),
        'total_trade_imports': Trade.objects.filter(import_source='csv_import').count(),
    }
    return Response(stats)


@api_view(['GET'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_user_list_view(request):
    """GET /api/admin/users/"""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    qs = User.objects.filter(deleted_at__isnull=True).order_by('-date_joined')

    # Filters
    sub_type = request.query_params.get('subscription_type')
    search = request.query_params.get('search')
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
    user.is_active = False
    user.save(update_fields=['deleted_at', 'is_active'])

    AdminUserAction.objects.create(
        admin=request.admin,
        target_user_id=user_id,
        action_type='delete',
        action_detail={'deleted_at': str(user.deleted_at)}
    )
    return Response(status=status.HTTP_204_NO_CONTENT)


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
        for field in ['full_name',  'access_level']:
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




# ─── Admin Rules Management ───────────────────────────────────────────────────

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


@api_view(['PUT', 'DELETE'])
@authentication_classes([])
@permission_classes([IsAdminAuthenticated])
def admin_rule_detail_view(request, pk):
    """PUT/DELETE /api/admin/rules/<id>/"""
    from rules.models import Rule
    from rules.serializers import RuleSerializer

    rule = Rule.objects.filter(pk=pk, is_admin_defined=True, deleted_at__isnull=True).first()
    if not rule:
        return Response({'error': 'Rule not found.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'PUT':
        for field in ['rule_name', 'description', 'category', 'rule_type', 'trigger_scope', 'trigger_condition', 'action', 'is_active']:
            if field in request.data:
                setattr(rule, field, request.data[field])
        rule.save()
        return Response(RuleSerializer(rule).data)
    elif request.method == 'DELETE':
        rule.deleted_at = timezone.now()
        rule.save()
        return Response(status=status.HTTP_204_NO_CONTENT)
