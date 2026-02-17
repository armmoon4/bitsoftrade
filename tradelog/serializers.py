from rest_framework import serializers
from tradelog.models import Trade


class TradeManagementSerializer(serializers.ModelSerializer):

    user_username = serializers.CharField(source="user.username", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Trade
        fields = "__all__"
        read_only_fields = ["user", "total_pnl", "created_at", "updated_at"]