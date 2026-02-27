from rest_framework import serializers
from .models import Mistake, TradeMistake


class MistakeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Mistake
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'is_admin_defined', 'created_by_admin']


class TradeMistakeSerializer(serializers.ModelSerializer):
    mistake_name = serializers.CharField(source='mistake.mistake_name', read_only=True)
    severity_weight = serializers.IntegerField(source='mistake.severity_weight', read_only=True)
    category = serializers.CharField(source='mistake.category', read_only=True)

    class Meta:
        model = TradeMistake
        fields = '__all__'
