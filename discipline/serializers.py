from rest_framework import serializers
from .models import DisciplineSession, ViolationsLog


class DisciplineSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DisciplineSession
        fields = '__all__'
        read_only_fields = ['id', 'user', 'session_state', 'violations_count',
                            'hard_violations', 'soft_violations', 'created_at', 'updated_at']


class ViolationsLogSerializer(serializers.ModelSerializer):
    rule_name = serializers.CharField(source='rule.rule_name', read_only=True)

    class Meta:
        model = ViolationsLog
        fields = '__all__'
