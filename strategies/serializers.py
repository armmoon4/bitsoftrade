from rest_framework import serializers
from .models import Strategy


class StrategySerializer(serializers.ModelSerializer):
    # Calculated performance fields — read only, populated by view
    total_trades = serializers.IntegerField(read_only=True, default=0)
    closed_trades = serializers.IntegerField(read_only=True, default=0)
    win_rate = serializers.FloatField(read_only=True, default=0)
    avg_return = serializers.FloatField(read_only=True, default=0)
    total_pnl = serializers.FloatField(read_only=True, default=0)
    profit_factor = serializers.FloatField(read_only=True, default=0)
    max_drawdown = serializers.FloatField(read_only=True, default=0)
    max_drawdown_pct = serializers.FloatField(read_only=True, default=0)
    sample_size_progress = serializers.FloatField(read_only=True, default=0)
    risk_reward_ratio = serializers.CharField(read_only=True, default='N/A')

    class Meta:
        model = Strategy
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by_admin', 'user', 'deleted_at']


class StrategyMinimalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Strategy
        fields = ['id', 'strategy_name']