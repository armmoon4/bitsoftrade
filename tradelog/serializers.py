from rest_framework import serializers
from tradelog.models import Trade


class TradeManagementSerializer(serializers.ModelSerializer):
    strategy_name = serializers.CharField(source='strategy.strategy_name', read_only=True, default=None)
    rules_followed = serializers.SerializerMethodField()
    mistakes = serializers.SerializerMethodField()

    class Meta:
        model = Trade
        exclude = ['deleted_at']
        read_only_fields = ['id', 'user', 'total_pnl', 'is_disciplined', 'session', 'created_at', 'updated_at']

    def get_rules_followed(self, obj):
        return list(obj.trade_rules.select_related('rule').values_list('rule__rule_name', flat=True))

    def get_mistakes(self, obj):
        return list(obj.trade_mistakes.select_related('mistake').values_list('mistake__mistake_name', flat=True))


class TradeSymbolSerializer(serializers.ModelSerializer):
    class Meta:
        model = Trade
        fields = ['id', 'symbol']


class ImageUploadSerializer(serializers.Serializer):
    images = serializers.ListField(
        child=serializers.ImageField(),
        allow_empty=False,
        help_text="Upload multiple images"
    )