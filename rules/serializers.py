from rest_framework import serializers
from .models import Rule


class RuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rule
        fields = '__all__'
        read_only_fields = [
            'id', 'created_at', 'updated_at',
            'is_admin_defined', 'created_by_admin',
            'user',  # users cannot assign rules to other users
        ]

    def validate(self, data):
        # Strip any attempt to smuggle admin-only fields
        data.pop('is_admin_defined', None)
        data.pop('created_by_admin', None)
        data.pop('user', None)
        return data
