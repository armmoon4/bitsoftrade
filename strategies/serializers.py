from rest_framework import serializers
from .models import Strategy


class StrategySerializer(serializers.ModelSerializer):
    # Calculated performance fields — read only, populated by view
    total_trades = serializers.IntegerField(read_only=True, default=0)
    win_rate = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True, default=0)
    total_pnl = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True, default=0)
    profit_factor = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True, default=0)
    sample_size_progress = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True, default=0)

    class Meta:
        model = Strategy
        fields = '__all__'
        read_only_fields = ['id', 'maturity_status', 'created_at', 'updated_at', 'created_by_admin' , 'user' , 'deleted_at']
