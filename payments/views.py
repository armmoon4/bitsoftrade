import hashlib
import hmac
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from rest_framework.decorators import api_view, permission_classes
from rest_framework import permissions, status
from rest_framework.response import Response

from .models import PaymentTransaction
from .serializers import PaymentTransactionSerializer


# Maps card_key → subscription_type on User model
CARD_KEY_TO_PLAN = {
    'discipline_tools': 'tool',
    'learning_hub':     'learning',
    'combo_monthly':    'both',
    'combo_annual':     'both',
}

# Maps card_key + billing_cycle → subscription duration in days
PLAN_DURATION_DAYS = {
    'discipline_tools_monthly': 30,
    'discipline_tools_yearly':  365,
    'learning_hub_biannual':    180,
    'combo_monthly_monthly':    30,
    'combo_annual_annual':      365,
}


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def create_order_view(request):
    """
    POST /api/payments/create-order/
    Body: { "card_key": "discipline_tools", "billing_cycle": "monthly" }
    """
    try:
        import razorpay
    except ImportError:
        return Response(
            {'error': 'Razorpay SDK not installed.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    from admin_panel.models import PricingPlan

    card_key      = request.data.get('card_key', '').strip()
    billing_cycle = request.data.get('billing_cycle', '').strip()

    if not card_key:
        return Response({'error': 'card_key is required.'}, status=status.HTTP_400_BAD_REQUEST)

    # ── Fetch live price from CMS ──────────────────────────────────────────
    plan = PricingPlan.objects.filter(card_key=card_key, is_active=True).first()
    if not plan:
        return Response({'error': 'Plan not found or inactive.'}, status=status.HTTP_404_NOT_FOUND)

    # discipline_tools has monthly/yearly toggle — others have single price
    if card_key == 'discipline_tools':
        if billing_cycle == 'yearly' and plan.price_yearly:
            amount_inr = plan.price_yearly
        else:
            billing_cycle = 'monthly'
            amount_inr = plan.price
    else:
        billing_cycle = plan.billing_cycle
        amount_inr = plan.price

    # Razorpay needs paise (multiply by 100)
    amount_paise = int(amount_inr * 100)

    # ── Resolve plan_type for user subscription ────────────────────────────
    plan_type = CARD_KEY_TO_PLAN.get(card_key)
    if not plan_type:
        return Response({'error': 'Invalid card_key.'}, status=status.HTTP_400_BAD_REQUEST)

    # ── Create Razorpay order ──────────────────────────────────────────────
    client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    razorpay_order = client.order.create(data={
        'amount':   amount_paise,
        'currency': 'INR',
        'receipt':  f'order_{request.user.id}_{card_key}',
        'notes':    {
            'user_id':       str(request.user.id),
            'plan_type':     plan_type,
            'card_key':      card_key,
            'billing_cycle': billing_cycle,
        },
    })

    txn = PaymentTransaction.objects.create(
        user=request.user,
        razorpay_order_id=razorpay_order['id'],
        amount=amount_inr,
        plan_type=plan_type,
        card_key=card_key,
        billing_cycle=billing_cycle,
        status='pending',
    )

    return Response({
        'order_id':       razorpay_order['id'],
        'amount':         amount_paise,          # paise for Razorpay JS
        'amount_display': float(amount_inr),     # rupees for UI display
        'currency':       'INR',
        'key':            settings.RAZORPAY_KEY_ID,
        'transaction_id': str(txn.id),
        'plan_name':      plan.name,
        'plan_type':      plan_type,
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def webhook_view(request):
    """POST /api/payments/webhook/ — Razorpay webhook (signature verified)."""
    webhook_secret    = getattr(settings, 'RAZORPAY_WEBHOOK_SECRET', '')
    webhook_signature = request.headers.get('X-Razorpay-Signature', '')
    payload           = request.body

    if webhook_secret:
        expected = hmac.new(
            webhook_secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, webhook_signature):
            return Response({'error': 'Invalid signature'}, status=status.HTTP_400_BAD_REQUEST)

    event          = request.data.get('event')
    payment_entity = request.data.get('payload', {}).get('payment', {}).get('entity', {})
    order_id       = payment_entity.get('order_id')

    if event == 'payment.captured' and order_id:
        try:
            txn = PaymentTransaction.objects.get(razorpay_order_id=order_id)

            if txn.status == 'success':       # idempotency guard
                return Response({'status': 'ok'})

            txn.razorpay_payment_id = payment_entity.get('id')
            txn.status              = 'success'
            txn.paid_at             = timezone.now()
            txn.save()

            # ── Update user subscription ───────────────────────────────────
            duration_key  = f'{txn.card_key}_{txn.billing_cycle}'
            duration_days = PLAN_DURATION_DAYS.get(duration_key, 365)

            user = txn.user
            user.subscription_type   = txn.plan_type
            user.subscription_status = 'active'
            user.subscription_start  = timezone.now()
            user.subscription_end    = timezone.now() + timedelta(days=duration_days)
            user.save(update_fields=[
                'subscription_type', 'subscription_status',
                'subscription_start', 'subscription_end',
            ])

        except PaymentTransaction.DoesNotExist:
            pass

    elif event == 'payment.failed' and order_id:
        PaymentTransaction.objects.filter(
            razorpay_order_id=order_id, status='pending'
        ).update(status='failed')

    return Response({'status': 'ok'})


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def payment_history_view(request):
    """GET /api/payments/history/"""
    transactions = PaymentTransaction.objects.filter(
        user=request.user
    ).order_by('-created_at')
    return Response(PaymentTransactionSerializer(transactions, many=True).data)