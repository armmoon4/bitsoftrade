from django.urls import path
from .views import create_order_view, webhook_view, payment_history_view

urlpatterns = [
    path('create-order/', create_order_view, name='payment-create-order'),
    path('webhook/', webhook_view, name='payment-webhook'),
    path('history/', payment_history_view, name='payment-history'),
]


