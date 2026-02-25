from rest_framework import serializers
from tradelog.models import Trade


class TradeManagementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Trade
        exclude = ['deleted_at']
        read_only_fields = ['id', 'user', 'total_pnl', 'is_disciplined', 'session', 'created_at', 'updated_at']