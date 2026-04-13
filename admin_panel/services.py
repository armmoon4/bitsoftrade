"""
admin_panel/services.py
───────────────────────
Pure business-logic functions.
"""

import calendar
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from .models import Admin, AdminUserAction, AdminAdminAction, Review, PricingPlan


# ─── Auth ──────────────────────────────────────────────────────────────────────

def authenticate_admin(email: str, password: str):
    """
    Returns the Admin if credentials are valid, otherwise None.
    Raises Admin.DoesNotExist only when the record is missing.
    """
    try:
        admin = Admin.objects.get(email=email, deleted_at__isnull=True)
    except Admin.DoesNotExist:
        return None
    return admin if admin.check_password(password) else None


# ─── Dashboard ─────────────────────────────────────────────────────────────────

def get_dashboard_stats():
    """
    Collect and return the full stats payload as a plain dict.
    All heavy DB work lives here so the view stays thin.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()

    now   = timezone.now()
    today = now.date()

    yesterday       = today - timedelta(days=1)
    week_start      = today - timedelta(days=6)
    prev_week_start = today - timedelta(days=13)
    prev_week_end   = today - timedelta(days=7)
    month_start     = today.replace(day=1)
    prev_month_start = (month_start - timedelta(days=1)).replace(day=1)
    prev_month_end   = month_start - timedelta(days=1)

    active_users = User.objects.filter(deleted_at__isnull=True)

    # ── user growth numbers ────────────────────────────────────────────────────
    total_users    = active_users.count()
    new_today      = active_users.filter(date_joined__date=today).count()
    new_yesterday  = active_users.filter(date_joined__date=yesterday).count()
    new_this_week  = active_users.filter(date_joined__date__gte=week_start).count()
    new_prev_week  = active_users.filter(
        date_joined__date__gte=prev_week_start,
        date_joined__date__lte=prev_week_end,
    ).count()
    new_this_month = active_users.filter(date_joined__date__gte=month_start).count()
    new_prev_month = active_users.filter(
        date_joined__date__gte=prev_month_start,
        date_joined__date__lte=prev_month_end,
    ).count()

    users_end_prev_month = active_users.filter(date_joined__date__lte=prev_month_end).count()
    growth_rate_pct = round((new_this_month / users_end_prev_month) * 100, 1) if users_end_prev_month else 0.0

    users_end_prev_prev_month = active_users.filter(date_joined__date__lt=prev_month_start).count()
    prev_growth_rate_pct = (
        round((new_prev_month / users_end_prev_prev_month) * 100, 1)
        if users_end_prev_prev_month else 0.0
    )

    def pct_change(current, previous):
        if previous == 0:
            return None
        return round(((current - previous) / previous) * 100, 1)

    user_growth = {
        'total_users': {
            'value':              total_users,
            'change_pct_month':   pct_change(new_this_month, new_prev_month),
        },
        'new_today': {
            'value':                new_today,
            'change_vs_yesterday':  new_today - new_yesterday,
        },
        'weekly_signups': {
            'value':           new_this_week,
            'change_pct_week': pct_change(new_this_week, new_prev_week),
        },
        'monthly_signups': {
            'value':            new_this_month,
            'change_pct_month': pct_change(new_this_month, new_prev_month),
        },
        'growth_rate': {
            'value':      growth_rate_pct,
            'change_mom': round(growth_rate_pct - prev_growth_rate_pct, 1),
        },
    }

    # ── platform engagement ────────────────────────────────────────────────────
    try:
        from tradelog.models import Trade
        trades_today  = Trade.objects.filter(deleted_at__isnull=True, entry_date__date=today).count()
        trades_per_user = round(trades_today / total_users, 1) if total_users else 0
    except Exception:
        trades_today = trades_per_user = 0

    try:
        from journal.models import JournalEntry
        journal_this_week = JournalEntry.objects.filter(
            deleted_at__isnull=True, created_at__date__gte=week_start
        ).count()
        journal_prev_week = JournalEntry.objects.filter(
            deleted_at__isnull=True,
            created_at__date__gte=prev_week_start,
            created_at__date__lte=prev_week_end,
        ).count()
        journal_change_pct = pct_change(journal_this_week, journal_prev_week)
    except Exception:
        journal_this_week  = 0
        journal_change_pct = None

    try:
        from strategies.models import Strategy
        strategies_total = Strategy.objects.filter(deleted_at__isnull=True, is_template=False).count()
    except Exception:
        strategies_total = 0

    try:
        dau = active_users.filter(
            Q(trades__entry_date__date=today) |
            Q(journal_entries__created_at__date=today)
        ).distinct().count()
    except Exception:
        dau = 0

    platform_engagement = {
        'daily_active_users': {
            'value':        dau,
            'pct_of_total': round((dau / total_users * 100), 1) if total_users else 0,
        },
        'avg_session_seconds': None,
        'trades_per_day': {
            'value':        trades_today,
            'per_user_avg': trades_per_user,
        },
        'journal_entries_this_week': {
            'value':            journal_this_week,
            'change_pct_week':  journal_change_pct,
        },
        'strategies_created': {
            'value': strategies_total,
        },
    }

    # ── charts ─────────────────────────────────────────────────────────────────
    monthly_trend = []
    for i in range(5, -1, -1):
        year  = now.year
        month = now.month - i
        while month <= 0:
            month += 12
            year  -= 1
        _, last_day = calendar.monthrange(year, month)
        ms    = timezone.datetime(year, month, 1, tzinfo=now.tzinfo)
        me    = timezone.datetime(year, month, last_day, 23, 59, 59, tzinfo=now.tzinfo)
        count = active_users.filter(date_joined__gte=ms, date_joined__lte=me).count()
        monthly_trend.append({'month': ms.strftime('%b'), 'signups': count})

    weekly_trend = []
    for i in range(7, -1, -1):
        ws    = today - timedelta(days=today.weekday()) - timedelta(weeks=i)
        we    = ws + timedelta(days=6)
        count = active_users.filter(date_joined__date__gte=ws, date_joined__date__lte=we).count()
        weekly_trend.append({'week': f'W{8 - i}', 'signups': count})

    return {
        'user_growth':         user_growth,
        'platform_engagement': platform_engagement,
        'charts': {
            'monthly_user_growth': monthly_trend,
            'weekly_signups':      weekly_trend,
        },
    }


# ─── User Management ───────────────────────────────────────────────────────────

def list_users(subscription_type=None, search=None):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    qs = User.objects.filter(deleted_at__isnull=True).order_by('-date_joined')
    if subscription_type:
        qs = qs.filter(subscription_type=subscription_type)
    if search:
        qs = qs.filter(Q(username__icontains=search) | Q(email__icontains=search))
    data = list(qs.values('id', 'username', 'email', 'subscription_type',
                           'subscription_status', 'is_active', 'date_joined'))
    return {'count': len(data), 'results': data}


def toggle_user_active(user_id, acting_admin):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user = User.objects.filter(pk=user_id, deleted_at__isnull=True).first()
    if not user:
        return None, None
    prev        = user.is_active
    user.is_active = not user.is_active
    user.save(update_fields=['is_active'])
    AdminUserAction.objects.create(
        admin=acting_admin,
        target_user_id=user_id,
        action_type='toggle_active',
        action_detail={'from': prev, 'to': user.is_active},
    )
    return user, user.is_active


def soft_delete_user(user_id, acting_admin):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user = User.objects.filter(pk=user_id, deleted_at__isnull=True).first()
    if not user:
        return False
    user.deleted_at = timezone.now()
    user.is_active  = False
    user.save(update_fields=['deleted_at', 'is_active'])
    AdminUserAction.objects.create(
        admin=acting_admin,
        target_user_id=user_id,
        action_type='delete',
        action_detail={'deleted_at': str(user.deleted_at)},
    )
    return True


# ─── Admin Management ──────────────────────────────────────────────────────────

def list_admins():
    return list(
        Admin.objects.filter(deleted_at__isnull=True)
        .values('id', 'full_name', 'email', 'access_level', 'created_at')
    )


def create_admin(data, acting_admin):
    """
    Returns (new_admin, None) on success, or (None, error_str) on failure.
    Caller is responsible for checking acting_admin.access_level beforehand.
    """
    required = ['full_name', 'email', 'password', 'access_level']
    for field in required:
        if not data.get(field):
            return None, f'{field} is required.'

    if Admin.objects.filter(email=data['email']).exists():
        return None, 'Email already in use.'

    new_admin = Admin(
        full_name=data['full_name'],
        email=data['email'],
        access_level=data['access_level'],
        created_by_admin=acting_admin,
    )
    new_admin.set_password(data['password'])
    new_admin.save()

    AdminAdminAction.objects.create(
        performed_by_admin=acting_admin,
        target_admin=new_admin,
        action_type='create',
        action_detail={'email': new_admin.email, 'access_level': new_admin.access_level},
    )
    return new_admin, None


def update_admin(admin_id, data, acting_admin):
    """Returns (target_admin, None) or (None, error_str)."""
    target = Admin.objects.filter(pk=admin_id, deleted_at__isnull=True).first()
    if not target:
        return None, 'Admin not found.'
    if str(target.id) == str(acting_admin.id):
        return None, 'Cannot modify your own account via this endpoint.'

    for field in ['full_name', 'access_level']:
        if field in data:
            setattr(target, field, data[field])
    if 'password' in data:
        target.set_password(data['password'])
    target.save()

    AdminAdminAction.objects.create(
        performed_by_admin=acting_admin,
        target_admin=target,
        action_type='edit',
        action_detail=data,
    )
    return target, None


def delete_admin(admin_id, acting_admin):
    """Returns True on success, False if not found. Raises ValueError on self-delete."""
    target = Admin.objects.filter(pk=admin_id, deleted_at__isnull=True).first()
    if not target:
        return False
    if str(target.id) == str(acting_admin.id):
        raise ValueError('Cannot modify your own account via this endpoint.')
    target.deleted_at = timezone.now()
    target.save()
    AdminAdminAction.objects.create(
        performed_by_admin=acting_admin,
        target_admin=target,
        action_type='delete',
        action_detail={},
    )
    return True


# ─── CMS: Reviews ──────────────────────────────────────────────────────────────

def create_review(data):
    """Returns (Review, None) or (None, error_str)."""
    for field in ['reviewer_name', 'review_text']:
        if not data.get(field):
            return None, f'{field} is required.'
    rating = int(data.get('rating', 5))
    if not (1 <= rating <= 5):
        return None, 'rating must be between 1 and 5.'
    review = Review.objects.create(
        reviewer_name=data['reviewer_name'],
        rating=rating,
        review_text=data['review_text'],
        is_visible=data.get('is_visible', True),
        display_order=int(data.get('display_order', 0)),
    )
    return review, None


def update_review(review, data):
    """Returns (Review, None) or (None, error_str)."""
    for field in ['reviewer_name', 'review_text', 'is_visible', 'display_order']:
        if field in data:
            setattr(review, field, data[field])
    if 'rating' in data:
        rating = int(data['rating'])
        if not (1 <= rating <= 5):
            return None, 'rating must be between 1 and 5.'
        review.rating = rating
    review.save()
    return review, None


def toggle_review_visibility(review):
    review.is_visible = not review.is_visible
    review.save(update_fields=['is_visible', 'updated_at'])
    return review


# ─── CMS: Pricing Plans ────────────────────────────────────────────────────────

def create_pricing_plan(data):
    """Returns (PricingPlan, None) or (None, error_str)."""
    for field in ['name', 'price']:
        if data.get(field) is None:
            return None, f'{field} is required.'
    valid_cycles  = [c[0] for c in PricingPlan.BILLING_CYCLE_CHOICES]
    billing_cycle = data.get('billing_cycle', 'monthly')
    if billing_cycle not in valid_cycles:
        return None, f'billing_cycle must be one of {valid_cycles}.'
    plan = PricingPlan.objects.create(
        name=data['name'],
        price=data['price'],
        billing_cycle=billing_cycle,
        is_popular=data.get('is_popular', False),
        is_active=data.get('is_active', True),
        features=data.get('features', []),
        display_order=int(data.get('display_order', 0)),
    )
    return plan, None


def update_pricing_plan(plan, data):
    """Returns (PricingPlan, None) or (None, error_str)."""
    for field in ['name', 'price', 'billing_cycle', 'is_popular',
                  'is_active', 'features', 'display_order']:
        if field in data:
            if field == 'billing_cycle':
                valid_cycles = [c[0] for c in PricingPlan.BILLING_CYCLE_CHOICES]
                if data[field] not in valid_cycles:
                    return None, f'billing_cycle must be one of {valid_cycles}.'
            setattr(plan, field, data[field])
    plan.save()
    return plan, None


def toggle_plan_active(plan):
    plan.is_active = not plan.is_active
    plan.save(update_fields=['is_active', 'updated_at'])
    return plan


# ─── Broadcast Notifications ───────────────────────────────────────────────────

def send_broadcast(title, message, recipients, acting_admin):
    """
    Fan-out a broadcast notification to matching users.
    Returns (AdminBroadcast, None) or (None, error_str).
    """
    from notifications.models import AdminBroadcast, Notification
    from django.contrib.auth import get_user_model
    User = get_user_model()

    valid_recipients = [r[0] for r in AdminBroadcast.RECIPIENT_CHOICES]
    if recipients not in valid_recipients:
        return None, f'recipients must be one of: {", ".join(valid_recipients)}.'

    active_users = User.objects.filter(is_active=True, deleted_at__isnull=True)
    if recipients == 'all':
        target_users = active_users
    elif recipients == 'pro':
        target_users = active_users.filter(subscription_type='pro')
    elif recipients == 'elite':
        target_users = active_users.filter(subscription_type='elite')
    elif recipients == 'pro_elite':
        target_users = active_users.filter(subscription_type__in=['pro', 'elite'])
    else:
        target_users = User.objects.none()

    notifications = [
        Notification(
            user=user,
            notification_type='admin_broadcast',
            severity='info',
            title=title,
            message=message,
        )
        for user in target_users
    ]
    Notification.objects.bulk_create(notifications, batch_size=500)

    broadcast = AdminBroadcast.objects.create(
        sent_by_admin=acting_admin,
        title=title,
        message=message,
        recipients=recipients,
        delivered_count=len(notifications),
    )
    return broadcast, None