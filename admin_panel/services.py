"""
admin_panel/services.py
───────────────────────
Pure business-logic functions.
"""

import calendar
import logging
from datetime import timedelta, datetime

logger = logging.getLogger(__name__)

from django.db.models import Q
from django.utils import timezone

from .models import Admin, AdminUserAction, AdminAdminAction, Review, PricingPlan , LearningModule, LearningTopic


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

        # trades_per_day: 7-day rolling average (total trades in last 7 days / 7)
        trades_last_7d  = Trade.objects.filter(
            deleted_at__isnull=True,
            trade_date__gte=week_start,
        ).count()
        trades_per_day  = round(trades_last_7d / 7, 1)
        trades_per_user = round(trades_per_day / total_users, 1) if total_users else 0

        # avg session duration: mean of (exit_time - entry_time) over last 7 days
        avg_session_seconds = None
        timed_trades = Trade.objects.filter(
            deleted_at__isnull=True,
            trade_date__gte=week_start,
            entry_time__isnull=False,
            exit_time__isnull=False,
        ).values_list('entry_time', 'exit_time')
        if timed_trades.exists():
            durations = []
            for entry_t, exit_t in timed_trades:
                entry_secs = entry_t.hour * 3600 + entry_t.minute * 60 + entry_t.second
                exit_secs  = exit_t.hour  * 3600 + exit_t.minute  * 60 + exit_t.second
                diff = exit_secs - entry_secs
                if diff > 0:
                    durations.append(diff)
            if durations:
                avg_session_seconds = round(sum(durations) / len(durations))
    except Exception as e:
        logger.error("[admin stats] trades block failed: %s", e, exc_info=True)
        trades_per_day = trades_per_user = 0
        avg_session_seconds = None

    try:
        from journal.models import DailyJournal
        journal_this_week = DailyJournal.objects.filter(
            journal_date__gte=week_start
        ).count()
        journal_prev_week = DailyJournal.objects.filter(
            journal_date__gte=prev_week_start,
            journal_date__lte=prev_week_end,
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
            Q(trades__trade_date=today) |
            Q(daily_journals__journal_date=today)
        ).distinct().count()
    except Exception:
        dau = 0

    platform_engagement = {
        'daily_active_users': {
            'value':        dau,
            'pct_of_total': round((dau / total_users * 100), 1) if total_users else 0,
        },
        'avg_session_seconds': avg_session_seconds,
        'trades_per_day': {
            'value':        trades_per_day,
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
        qs = qs.filter(Q(first_name__icontains=search) | Q(last_name__icontains=search) | Q(email__icontains=search))
    data = list(qs.values('id', 'first_name', 'last_name', 'email', 'subscription_type',
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

VALID_CARD_KEYS = ['discipline_tools', 'learning_hub', 'combo_monthly', 'combo_annual']

def create_pricing_plan(data):
    """
    Returns (PricingPlan, None) or (None, error_str).

    Required fields: card_key, name, price
    Optional:        price_yearly (only meaningful for discipline_tools),
                     billing_cycle, tagline, badge, cta_label, footer_note,
                     features, is_popular, is_active, display_order
    """
    card_key = data.get('card_key', '').strip()
    if not card_key:
        return None, 'card_key is required.'
    if card_key not in VALID_CARD_KEYS:
        return None, f'card_key must be one of {VALID_CARD_KEYS}.'
    if PricingPlan.objects.filter(card_key=card_key).exists():
        return None, f'A plan with card_key "{card_key}" already exists. Use PUT to update it.'

    if data.get('price') is None:
        return None, 'price is required.'
    if not data.get('name', '').strip():
        return None, 'name is required.'

    valid_cycles  = [c[0] for c in PricingPlan.BILLING_CYCLE_CHOICES]
    billing_cycle = data.get('billing_cycle', 'monthly')
    if billing_cycle not in valid_cycles:
        return None, f'billing_cycle must be one of {valid_cycles}.'

    plan = PricingPlan.objects.create(
        card_key      = card_key,
        name          = data['name'].strip(),
        tagline       = data.get('tagline', '').strip(),
        badge         = data.get('badge', '').strip(),
        cta_label     = data.get('cta_label', '').strip(),
        footer_note   = data.get('footer_note', '').strip(),
        price         = data['price'],
        price_yearly  = data.get('price_yearly'),   # None is fine for non-DT cards
        billing_cycle = billing_cycle,
        is_popular    = data.get('is_popular', False),
        is_active     = data.get('is_active', True),
        features      = data.get('features', []),
        display_order = int(data.get('display_order', 0)),
    )
    return plan, None


def update_pricing_plan(plan, data):
    """
    Returns (PricingPlan, None) or (None, error_str).
    card_key is immutable after creation — ignore it silently if sent.
    """
    editable_fields = [
        'name', 'tagline', 'badge', 'cta_label', 'footer_note',
        'price', 'price_yearly', 'is_popular', 'is_active',
        'features', 'display_order',
    ]
    for field in editable_fields:
        if field in data:
            value = data[field]
            if field == 'name' and not str(value).strip():
                return None, 'name cannot be blank.'
            setattr(plan, field, value)

    if 'billing_cycle' in data:
        valid_cycles = [c[0] for c in PricingPlan.BILLING_CYCLE_CHOICES]
        if data['billing_cycle'] not in valid_cycles:
            return None, f'billing_cycle must be one of {valid_cycles}.'
        plan.billing_cycle = data['billing_cycle']

    plan.save()
    return plan, None


def toggle_plan_active(plan):
    plan.is_active = not plan.is_active
    plan.save(update_fields=['is_active', 'updated_at'])
    return plan


# ─── CMS: Learning Hub 

def list_learning_modules(visible_only=False):
    """Return all modules with their topics prefetched (1 extra query, not N)."""
    from .models import LearningModule
    qs = LearningModule.objects.prefetch_related('topics')
    if visible_only:
        qs = qs.filter(is_visible=True)
    return list(qs)


def create_learning_module(data):
    """Returns (LearningModule, None) or (None, error_str)."""
    from .models import LearningModule
    if not data.get('title', '').strip():
        return None, 'title is required.'
    module = LearningModule.objects.create(
        title=data['title'].strip(),
        subtitle=data.get('subtitle', '').strip(),
        display_order=int(data.get('display_order', 0)),
        is_visible=data.get('is_visible', True),
    )
    return module, None


def update_learning_module(module, data):
    """Returns (LearningModule, None) or (None, error_str)."""
    if 'title' in data:
        if not data['title'].strip():
            return None, 'title cannot be blank.'
        module.title = data['title'].strip()
    for field in ['subtitle', 'display_order', 'is_visible']:
        if field in data:
            setattr(module, field, data[field])
    module.save()
    return module, None


def toggle_module_visibility(module):
    module.is_visible = not module.is_visible
    module.save(update_fields=['is_visible', 'updated_at'])
    return module


# ── Topics ────────────────────────────────────────────────────────────────────

def list_topics_for_module(module, visible_only=False):
    """Return topics for a given module."""
    qs = module.topics.all()
    if visible_only:
        qs = qs.filter(is_visible=True)
    return list(qs)


def create_learning_topic(module, data):
    """Returns (LearningTopic, None) or (None, error_str)."""
    from .models import LearningTopic
    if not data.get('title', '').strip():
        return None, 'title is required.'
    topic = LearningTopic.objects.create(
        module=module,
        title=data['title'].strip(),
        display_order=int(data.get('display_order', 0)),
        is_visible=data.get('is_visible', True),
    )
    return topic, None


def update_learning_topic(topic, data):
    """Returns (LearningTopic, None) or (None, error_str)."""
    if 'title' in data:
        if not data['title'].strip():
            return None, 'title cannot be blank.'
        topic.title = data['title'].strip()
    for field in ['display_order', 'is_visible']:
        if field in data:
            setattr(topic, field, data[field])
    topic.save()
    return topic, None


def toggle_topic_visibility(topic):
    topic.is_visible = not topic.is_visible
    topic.save(update_fields=['is_visible', 'updated_at'])
    return topic


def bulk_create_topics(module, topics_data):
    """
    Bulk-insert a list of topic dicts under a module.
    Returns (list[LearningTopic], None) or (None, error_str).
    Used when seeding an entire module's curriculum at once.
    """
    from .models import LearningTopic
    if not isinstance(topics_data, list) or not topics_data:
        return None, 'topics must be a non-empty list.'
    objs = []
    for i, item in enumerate(topics_data):
        title = (item.get('title') or '').strip()
        if not title:
            return None, f'topics[{i}].title is required.'
        objs.append(LearningTopic(
            module=module,
            title=title,
            display_order=int(item.get('display_order', i)),
            is_visible=item.get('is_visible', True),
        ))
    created = LearningTopic.objects.bulk_create(objs)
    return created, None


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



#subscription type changes from admin
from django.contrib.auth import get_user_model
User = get_user_model()

def update_user_subscription(user_id, admin, data: dict):
    """
    Admin manually sets a user's subscription.
    data keys:
        subscription_type   : 'none' | 'tool' | 'learning' | 'both'
        subscription_status : 'active' | 'expired' | 'cancelled'
        is_lifetime         : bool  — if True, subscription_end is set to None
        subscription_end    : ISO datetime string (ignored when is_lifetime=True)
    """
    user = User.objects.filter(pk=user_id, deleted_at__isnull=True).first()
    if user is None:
        return None, 'User not found.'

    allowed_types    = {'none', 'tool', 'learning', 'both'}
    allowed_statuses = {'active', 'expired', 'cancelled'}

    sub_type = data.get('subscription_type')
    sub_status = data.get('subscription_status', 'active')

    if sub_type not in allowed_types:
        return None, f'Invalid subscription_type. Choose from {allowed_types}.'
    if sub_status not in allowed_statuses:
        return None, f'Invalid subscription_status. Choose from {allowed_statuses}.'

    user.subscription_type   = sub_type
    user.subscription_status = sub_status
    user.subscription_start  = timezone.now()

    if data.get('is_lifetime') or sub_type == 'none':
        user.subscription_end = None          # None = no expiry = lifetime
    else:
        end = data.get('subscription_end')
        if not end:
            return None, 'subscription_end is required unless is_lifetime is true.'
        try:
            from django.utils.dateparse import parse_datetime
            parsed = parse_datetime(end)
            if parsed is None:
                raise ValueError
            user.subscription_end = parsed
        except ValueError:
            return None, 'Invalid subscription_end datetime format. Use ISO 8601.'

    user.save()

    # Audit log
    AdminUserAction.objects.create(
        admin=admin,
        target_user_id=user.pk,
        action_type='update_subscription',
        action_detail={
            'subscription_type':   user.subscription_type,
            'subscription_status': user.subscription_status,
            'subscription_start':  str(user.subscription_start),
            'subscription_end':    str(user.subscription_end),
            'is_lifetime':         user.subscription_end is None,
        },
    )

    return user, None