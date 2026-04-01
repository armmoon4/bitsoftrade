from rest_framework import serializers
from .models import DailyJournal, TradeNote, PsychologyLog, SessionRecap, LearningNote 
from discipline.models import DisciplineSession

class DailyJournalSerializer(serializers.ModelSerializer):
    session_state = serializers.SerializerMethodField()

    class Meta:
        model = DailyJournal
        fields = "__all__"
        read_only_fields = ["user", "created_at", "updated_at"]

    def get_session_state(self, obj):
        active_session = self.context.get('active_session')
        if active_session:
            return active_session.session_state
        return None


class TradeNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = TradeNote
        fields = "__all__"
        read_only_fields = ["user", "created_at", "updated_at"]


class PsychologyLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = PsychologyLog
        fields = "__all__"
        read_only_fields = ["user", "created_at"]


class SessionRecapSerializer(serializers.ModelSerializer):
    class Meta:
        model = SessionRecap
        fields = "__all__"
        read_only_fields = ["user", "created_at"]


class LearningNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = LearningNote
        fields = "__all__"
        read_only_fields = ["user", "created_at"]
