from rest_framework import serializers
from tradelog.models import Trade


class TradeManagementSerializer(serializers.ModelSerializer):
    strategy_name = serializers.CharField(source='strategy.strategy_name', read_only=True, default=None)
    class Meta:
        model = Trade
        exclude = ['deleted_at']
        read_only_fields = ['id', 'user', 'total_pnl', 'is_disciplined', 'session', 'created_at', 'updated_at']


class TradeSymbolSerializer(serializers.ModelSerializer):
    class Meta:
        model = Trade
        fields = ['id', 'symbol']        


class ImageUploadSerializer(serializers.Serializer):
    # Change this to accept a list of images instead of just one
    images = serializers.ListField(
        child=serializers.ImageField(),
        allow_empty=False,
        help_text="Upload multiple images"
    )   