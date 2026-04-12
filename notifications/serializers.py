from rest_framework import serializers
from notifications.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    rule_name = serializers.SerializerMethodField()
    rule_id = serializers.SerializerMethodField()
    trade_id = serializers.SerializerMethodField()
    session_id = serializers.SerializerMethodField()
    session_date = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            'id',
            'notification_type',
            'severity',
            'title',
            'message',
            'is_read',
            'rule_id',
            'rule_name',
            'session_id',
            'session_date',
            'trade_id',
            'created_at',
        ]
        read_only_fields = fields

    def get_rule_name(self, obj):
        return obj.rule.rule_name if obj.rule else None

    def get_rule_id(self, obj):
        return str(obj.rule.id) if obj.rule else None

    def get_trade_id(self, obj):
        return str(obj.trade.id) if obj.trade else None

    def get_session_id(self, obj):
        return str(obj.session.id) if obj.session else None

    def get_session_date(self, obj):
        return str(obj.session.session_date) if obj.session else None



from notifications.models import Notification, NotificationSettings

class NotificationSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationSettings
        fields = [
            'notify_rule_triggered',
            'notify_rule_violated',
            'notify_session_locked',
            'notify_session_unlocked',
            'auto_delete_after_days',
            'updated_at',
        ]
        read_only_fields = ['updated_at']