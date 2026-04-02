from rest_framework import serializers
from .models import Rule

class RuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rule
        fields = '__all__'
        read_only_fields = [
            'id', 'created_at', 'updated_at',
            'is_admin_defined', 'created_by_admin',
            'user',       
            'deleted_at', 
        ]

    def validate(self, data):
        data.pop('is_admin_defined', None)
        data.pop('created_by_admin', None)
        data.pop('user', None)
        return data

# rules list serializer
class RuleTitleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rule
        fields = ['id', 'rule_name'] # Replace 'rule_name' with 'title' if that is your model field