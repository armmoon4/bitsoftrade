from rest_framework import serializers
from .models import UserMetricSnapshot


class MetricsSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserMetricSnapshot
        fields = '__all__'
        read_only_fields = ['id', 'user', 'calculated_at']
