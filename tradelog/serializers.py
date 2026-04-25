from rest_framework import serializers
from tradelog.models import Trade


class TradeManagementSerializer(serializers.ModelSerializer):
    strategy_name = serializers.CharField(source='strategy.strategy_name', read_only=True, default=None)
    # Accepts a list of Rule UUIDs on write; to_representation converts back to names on read.
    rules_followed = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list
    )
    # Accepts a list of Mistake UUIDs on write; to_representation converts back to names on read.
    mistakes = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list
    )
    rules_violation = serializers.SerializerMethodField()

    class Meta:
        model = Trade
        exclude = ['deleted_at']
        read_only_fields = ['id', 'user', 'total_pnl', 'is_disciplined', 'session', 'created_at', 'updated_at']

    def to_representation(self, instance):
        """On read: return rule/mistake names from the junction tables (same as before)."""
        ret = super().to_representation(instance)
        ret['rules_followed'] = list(
            instance.trade_rules.select_related('rule')
            .values_list('rule__rule_name', flat=True)
        )
        ret['mistakes'] = list(
            instance.trade_mistakes.select_related('mistake')
            .values_list('mistake__mistake_name', flat=True)
        )
        return ret

    # ── Junction-table sync helpers ───────────────────────────────────────────

    def _sync_rules(self, trade, rule_ids):
        from rules.models import TradeRule, Rule
        TradeRule.objects.filter(trade=trade).delete()
        for rule_id in rule_ids:
            try:
                rule = Rule.objects.get(id=rule_id)
                TradeRule.objects.get_or_create(trade=trade, rule=rule)
            except Rule.DoesNotExist:
                pass

    def _sync_mistakes(self, trade, mistake_ids):
        from mistakes.models import TradeMistake, Mistake
        TradeMistake.objects.filter(trade=trade).delete()
        for mistake_id in mistake_ids:
            try:
                mistake = Mistake.objects.get(id=mistake_id)
                TradeMistake.objects.get_or_create(trade=trade, mistake=mistake)
            except Mistake.DoesNotExist:
                pass

    # ── Write overrides ───────────────────────────────────────────────────────

    def create(self, validated_data):
        rule_ids = validated_data.pop('rules_followed', [])
        mistake_ids = validated_data.pop('mistakes', [])
        trade = super().create(validated_data)
        self._sync_rules(trade, rule_ids)
        self._sync_mistakes(trade, mistake_ids)
        return trade

    def update(self, instance, validated_data):
        rule_ids = validated_data.pop('rules_followed', None)
        mistake_ids = validated_data.pop('mistakes', None)
        trade = super().update(instance, validated_data)
        if rule_ids is not None:
            self._sync_rules(trade, rule_ids)
        if mistake_ids is not None:
            self._sync_mistakes(trade, mistake_ids)
        return trade

    def get_rules_violation(self, obj):
        """
        Return a list of violated rule names for this trade.
        Sourced from ViolationsLog entries linked to this trade
        via the 'violation_logs' reverse relation.
        """
        return list(
            obj.violation_logs
            .select_related('rule')
            .values_list('rule__rule_name', flat=True)
        )



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