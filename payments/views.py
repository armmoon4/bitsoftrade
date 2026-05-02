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


PLAN_PRICES = {
    'tool': 99900,       # ₹999  in paise
    'learning': 49900,   # ₹499  in paise
    'both': 139900,      # ₹1399 in paise
}


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def create_order_view(request):
    """POST /api/payments/create-order/ — create a Razorpay order."""
    try:
        import razorpay
    except ImportError:
        return Response(
            {'error': 'Razorpay SDK not installed. Run: pip install razorpay'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    plan_type = request.data.get('plan_type')
    if plan_type not in PLAN_PRICES:
        return Response(
            {'error': f'Invalid plan_type. Choose from: {list(PLAN_PRICES.keys())}'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    amount = PLAN_PRICES[plan_type]
    client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

    order_data = {
        'amount': amount,
        'currency': 'INR',
        'receipt': f'order_{request.user.id}_{plan_type}',
        'notes': {'user_id': str(request.user.id), 'plan_type': plan_type},
    }
    razorpay_order = client.order.create(data=order_data)

    txn = PaymentTransaction.objects.create(
        user=request.user,
        razorpay_order_id=razorpay_order['id'],
        amount=amount / 100,   # store in rupees, not paise
        plan_type=plan_type,
        status='pending',
    )

    return Response({
        'order_id': razorpay_order['id'],
        'amount': amount,
        'currency': 'INR',
        'key': settings.RAZORPAY_KEY_ID,
        'transaction_id': str(txn.id),
    }, status=status.HTTP_201_CREATED)


# Removed @csrf_exempt — it was silently ignored when placed outside
# @api_view. DRF does not enforce CSRF for non-session auth requests, so
# AllowAny webhook endpoints don't need it. It was providing false confidence.
@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def webhook_view(request):
    """POST /api/payments/webhook/ — Razorpay webhook (signature verified)."""
    webhook_secret = getattr(settings, 'RAZORPAY_WEBHOOK_SECRET', '')
    webhook_signature = request.headers.get('X-Razorpay-Signature', '')
    payload = request.body

    if webhook_secret:
        expected = hmac.new(
            webhook_secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, webhook_signature):
            return Response({'error': 'Invalid signature'}, status=status.HTTP_400_BAD_REQUEST)

    event = request.data.get('event')
    payment_entity = request.data.get('payload', {}).get('payment', {}).get('entity', {})
    order_id = payment_entity.get('order_id')

    if event == 'payment.captured' and order_id:
        try:
            txn = PaymentTransaction.objects.get(razorpay_order_id=order_id)

            # Idempotency guard — Razorpay retries webhooks on timeout.
            # Without this, a duplicate event re-extends the subscription
            # by another 365 days on every retry.
            if txn.status == 'success':
                return Response({'status': 'ok'})

            txn.razorpay_payment_id = payment_entity.get('id')
            txn.status = 'success'
            txn.paid_at = timezone.now()
            txn.save()

            user = txn.user
            user.subscription_type = txn.plan_type
            user.subscription_status = 'active'
            user.subscription_start = timezone.now()
            user.subscription_end = timezone.now() + timedelta(days=365)
            user.save(update_fields=[
                'subscription_type', 'subscription_status',
                'subscription_start', 'subscription_end',
            ])
        except PaymentTransaction.DoesNotExist:
            pass

    elif event == 'payment.failed' and order_id:
        # Only update to failed if still pending — don't overwrite a success
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