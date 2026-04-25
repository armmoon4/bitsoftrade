from rest_framework import serializers
from tradelog.models import Trade


class TradeManagementSerializer(serializers.ModelSerializer):
    strategy_name = serializers.CharField(source='strategy.strategy_name', read_only=True, default=None)
    rules_followed = serializers.SerializerMethodField()
    mistakes = serializers.SerializerMethodField()
    rules_violation = serializers.SerializerMethodField()

    class Meta:
        model = Trade
        exclude = ['deleted_at']
        read_only_fields = ['id', 'user', 'total_pnl', 'is_disciplined', 'session', 'created_at', 'updated_at']

    def get_rules_followed(self, obj):
        return list(obj.trade_rules.select_related('rule').values_list('rule__rule_name', flat=True))

    def get_mistakes(self, obj):
        return list(obj.trade_mistakes.select_related('mistake').values_list('mistake__mistake_name', flat=True))

    def get_rules_violation(self, obj):
        return list(
            obj.violation_logs
            .select_related('rule')
            .values_list('rule__rule_name', flat=True)
        )

    def create(self, validated_data):
        request = self.context.get('request')
        rules_ids = request.data.get('rules_followed', []) if request else []
        mistakes_ids = request.data.get('mistakes', []) if request else []

        trade = super().create(validated_data)
        self._sync_rules_and_mistakes(trade, rules_ids, mistakes_ids)
        return trade

    def update(self, instance, validated_data):
        request = self.context.get('request')
        rules_ids = request.data.get('rules_followed', []) if request else []
        mistakes_ids = request.data.get('mistakes', []) if request else []

        trade = super().update(instance, validated_data)
        self._sync_rules_and_mistakes(trade, rules_ids, mistakes_ids)
        return trade

    def _sync_rules_and_mistakes(self, trade, rules_ids, mistakes_ids):
        from strategies.models import TradeRule, TradeMistake  

        if rules_ids:
            trade.trade_rules.all().delete()
            for rule_id in rules_ids:
                TradeRule.objects.create(trade=trade, rule_id=rule_id)

        if mistakes_ids:
            trade.trade_mistakes.all().delete()
            for mistake_id in mistakes_ids:
                TradeMistake.objects.create(trade=trade, mistake_id=mistake_id)