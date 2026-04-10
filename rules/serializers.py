from rest_framework import serializers
from .models import Rule, TradeRule


class RuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rule
        fields = '__all__'
        read_only_fields = [
            'id', 'created_at', 'updated_at',
            'is_admin_defined', 'created_by_admin',
            'is_system_rule',
            'user',
            'deleted_at',
        ]

    def validate(self, data):
        data.pop('is_admin_defined', None)
        data.pop('created_by_admin', None)
        data.pop('is_system_rule', None)
        data.pop('user', None)
        return data


class RuleTitleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rule
        fields = ['id', 'rule_name']


class SystemRuleUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for system rules.

    Editable fields   : category, rule_type, trigger_scope, action, is_active,
                        and the THRESHOLD VALUE inside trigger_condition.
    Locked fields     : rule_name, description, and the condition KEY itself
                        (e.g. maxLoss, maxTrades) — only the number may change.
    Never allowed     : delete (blocked in view).
    """

    class Meta:
        model = Rule
        fields = [
            'id',
            'rule_name',
            'description',
            'category',
            'rule_type',
            'trigger_scope',
            'trigger_condition',
            'action',
            'is_active',
            'is_system_rule',
            'is_admin_defined',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'rule_name',
            'description',
            'is_system_rule',
            'is_admin_defined',
            'created_at',
            'updated_at',
        ]

    def validate_trigger_condition(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("trigger_condition must be a JSON object.")

        # The existing condition key is fixed — user cannot change or add keys.
        existing = self.instance.trigger_condition or {}
        existing_keys = set(existing.keys())
        incoming_keys = set(value.keys())

        if incoming_keys != existing_keys:
            raise serializers.ValidationError(
                f"You can only update the threshold value. "
                f"Expected key: {existing_keys}, got: {incoming_keys}."
            )

        # The value must be a positive number.
        key = next(iter(incoming_keys))
        threshold = value[key]
        try:
            threshold = float(threshold)
        except (TypeError, ValueError):
            raise serializers.ValidationError(
                f"The value for '{key}' must be a positive number."
            )
        if threshold <= 0:
            raise serializers.ValidationError(
                f"The value for '{key}' must be greater than 0."
            )

        return {key: threshold}
    

class TradeRuleSerializer(serializers.ModelSerializer):
    rule_name = serializers.CharField(source='rule.rule_name', read_only=True)
    category = serializers.CharField(source='rule.category', read_only=True)
    rule_type = serializers.CharField(source='rule.rule_type', read_only=True)

    class Meta:
        model = TradeRule
        fields = '__all__'