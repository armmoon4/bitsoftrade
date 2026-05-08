import hashlib
import hmac
import logging
from datetime import timedelta

import razorpay
from admin_panel.models import PricingPlan

from django.conf import settings
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from rest_framework.decorators import api_view, permission_classes
from rest_framework import permissions, status
from rest_framework.response import Response

from .models import PaymentTransaction
from .serializers import PaymentTransactionSerializer

logger = logging.getLogger(__name__)


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

    Returns order_id, amount (paise), currency, key (Razorpay public key ID)
    — frontend must pass ALL of these to Razorpay JS checkout.
    """
    card_key      = request.data.get('card_key', '').strip()
    billing_cycle = request.data.get('billing_cycle', '').strip()

    if not card_key:
        return Response({'error': 'card_key is required.'}, status=status.HTTP_400_BAD_REQUEST)

    # ── Resolve plan_type early so we fail fast on bad card_key ───────────
    plan_type = CARD_KEY_TO_PLAN.get(card_key)
    if not plan_type:
        return Response({'error': 'Invalid card_key.'}, status=status.HTTP_400_BAD_REQUEST)

    # ── Fetch live price from CMS ──────────────────────────────────────────
    plan = PricingPlan.objects.filter(card_key=card_key, is_active=True).first()
    if not plan:
        return Response({'error': 'Plan not found or inactive.'}, status=status.HTTP_404_NOT_FOUND)

    # discipline_tools has monthly/yearly toggle — others have a single price
    if card_key == 'discipline_tools':
        if billing_cycle == 'yearly' and plan.price_yearly:
            amount_inr = plan.price_yearly
        else:
            billing_cycle = 'monthly'
            amount_inr    = plan.price
    else:
        billing_cycle = plan.billing_cycle
        amount_inr    = plan.price

    # Razorpay needs paise (INR × 100)
    amount_paise = int(amount_inr * 100)

    # ── Create Razorpay order ──────────────────────────────────────────────
    # wrapped in try/except — Razorpay API can fail (network, auth, etc.)
    try:
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
    except razorpay.errors.BadRequestError as e:
        logger.error('Razorpay bad request: %s', e)
        return Response({'error': 'Invalid payment request.'},
                        status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.exception('Razorpay order creation failed: %s', e)
        return Response({'error': 'Payment gateway error. Please try again.'},
                        status=status.HTTP_502_BAD_GATEWAY)

    # ── Save pending transaction ───────────────────────────────────────────
    txn = PaymentTransaction.objects.create(
        user=request.user,
        razorpay_order_id=razorpay_order['id'],
        amount=amount_inr,
        plan_type=plan_type,
        card_key=card_key,
        billing_cycle=billing_cycle,
        status='pending',
    )

    # ── Return everything frontend needs to open Razorpay checkout ─────────
    #  'key' (RAZORPAY_KEY_ID) is the PUBLIC key — safe to send to frontend.
    # Frontend MUST pass this as `key` when calling new Razorpay(options).open()
    # WITHOUT this key, Razorpay cannot identify your account → domain check fails.
    return Response({
        'order_id':       razorpay_order['id'],   # pass to Razorpay JS as order_id
        'amount':         amount_paise,            # pass to Razorpay JS as amount
        'currency':       'INR',
        'key':            settings.RAZORPAY_KEY_ID,  # pass to Razorpay JS as key
        'transaction_id': str(txn.id),
        'amount_display': float(amount_inr),       # rupees — for UI display only
        'plan_name':      plan.name,
        'plan_type':      plan_type,
    }, status=status.HTTP_201_CREATED)


#  @csrf_exempt is required — Razorpay is an external service and does not
# send a CSRF token. Without this, Django returns 403 for every webhook POST.
@csrf_exempt
@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def webhook_view(request):
    """
    POST /api/payments/webhook/
    Razorpay webhook — signature verified via HMAC-SHA256.
    Handles: payment.captured, payment.failed
    """
    webhook_secret    = getattr(settings, 'RAZORPAY_WEBHOOK_SECRET', '')
    webhook_signature = request.headers.get('X-Razorpay-Signature', '')
    payload           = request.body  # raw bytes — must be read before DRF parses it

    # ── Verify webhook signature ───────────────────────────────────────────
    #   `hmac.new(...)` — correct Python call is `hmac.new(key, msg, digestmod)`
    # Both are the same function but explicitly calling it correctly for clarity.
    if webhook_secret:
        expected = hmac.new(
            webhook_secret.encode('utf-8'),
            payload,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected, webhook_signature):
            logger.warning('Razorpay webhook signature mismatch.')
            return Response({'error': 'Invalid signature'}, status=status.HTTP_400_BAD_REQUEST)

    event          = request.data.get('event')
    payment_entity = request.data.get('payload', {}).get('payment', {}).get('entity', {})
    order_id       = payment_entity.get('order_id')

    # ── payment.captured ──────────────────────────────────────────────────
    if event == 'payment.captured' and order_id:
        try:
            txn = PaymentTransaction.objects.get(razorpay_order_id=order_id)

            if txn.status == 'success':
                # Idempotency guard — Razorpay can send duplicate webhook events
                return Response({'status': 'ok'})

            txn.razorpay_payment_id = payment_entity.get('id')
            txn.status              = 'success'
            txn.paid_at             = timezone.now()
            txn.save(update_fields=['razorpay_payment_id', 'status', 'paid_at'])

            # ── Activate user subscription ─────────────────────────────────
            duration_key  = f'{txn.card_key}_{txn.billing_cycle}'
            duration_days = PLAN_DURATION_DAYS.get(duration_key, 365)
            now           = timezone.now()

            user = txn.user
            user.subscription_type   = txn.plan_type
            user.subscription_status = 'active'
            user.subscription_start  = now
            user.subscription_end    = now + timedelta(days=duration_days)
            user.save(update_fields=[
                'subscription_type',
                'subscription_status',
                'subscription_start',
                'subscription_end',
            ])

            logger.info(
                'Payment captured: user=%s plan=%s duration=%d days',
                user.email, txn.plan_type, duration_days,
            )

        except PaymentTransaction.DoesNotExist:
            # Log it — could be a test event or an order created outside the app
            logger.warning('Webhook payment.captured: order_id %s not found.', order_id)

        except Exception as e:
            logger.exception('Error processing payment.captured for order %s: %s', order_id, e)
            # Still return 200 so Razorpay does not keep retrying
            return Response({'status': 'error'}, status=status.HTTP_200_OK)

    # ── payment.failed ────────────────────────────────────────────────────
    elif event == 'payment.failed' and order_id:
        updated = PaymentTransaction.objects.filter(
            razorpay_order_id=order_id,
            status='pending',
        ).update(status='failed')
        logger.info('Payment failed: order_id=%s rows_updated=%d', order_id, updated)

    return Response({'status': 'ok'})


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def payment_history_view(request):
    """GET /api/payments/history/"""
    transactions = PaymentTransaction.objects.filter(
        user=request.user,
    ).order_by('-created_at')
    return Response(PaymentTransactionSerializer(transactions, many=True).data)