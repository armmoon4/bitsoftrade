from rest_framework import serializers
from .models import DisciplineSession, ViolationsLog


class DisciplineSessionSerializer(serializers.ModelSerializer):
    """
    Serializer for DisciplineSession.

    Adds `trades_tag_status` — a computed field that shows live tagging
    progress for the Discipline Check panel.  The frontend can poll
    GET /api/discipline/current-session/ and update checklist checkmarks
    without any extra endpoint.

    trades_tag_status shape:
    {
        "flagged_count":    <int>  — total trades with a ViolationsLog entry,
        "tagged_count":     <int>  — how many of those have is_tagged_complete=True,
        "all_tagged":       <bool> — True when tagged_count == flagged_count,
        "untagged_trade_ids": [<uuid>, ...]  — IDs still needing to be tagged
    }
    """

    trades_tag_status = serializers.SerializerMethodField()

    class Meta:
        model = DisciplineSession
        fields = '__all__'
        read_only_fields = ['id', 'user', 'session_state', 'violations_count',
                            'hard_violations', 'soft_violations', 'created_at', 'updated_at']

    def get_trades_tag_status(self, obj):
        from mistakes.models import TradeMistake

        # All trade IDs that have at least one ViolationsLog entry for this session
        flagged_ids = list(
            obj.violation_logs
            .filter(trade__isnull=False)
            .values_list('trade_id', flat=True)
            .distinct()
        )

        total = len(flagged_ids)
        if total == 0:
            return {
                'flagged_count': 0,
                'tagged_count': 0,
                'all_tagged': True,
                'untagged_trade_ids': [],
            }

        # Trades that already have at least one mistake tagged
        trades_with_mistake = set(
            TradeMistake.objects
            .filter(trade_id__in=flagged_ids)
            .values_list('trade_id', flat=True)
            .distinct()
        )

        untagged_ids = [
            str(fid) for fid in flagged_ids
            if fid not in trades_with_mistake
        ]

        tagged_count = total - len(untagged_ids)

        return {
            'flagged_count': total,
            'tagged_count': tagged_count,
            'all_tagged': len(untagged_ids) == 0,
            'untagged_trade_ids': untagged_ids,
        }


class ViolationsLogSerializer(serializers.ModelSerializer):
    rule_name = serializers.CharField(source='rule.rule_name', read_only=True)

    class Meta:
        model = ViolationsLog
        fields = '__all__'
