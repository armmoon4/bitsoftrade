from rest_framework import serializers
from .models import DailyJournal, TradeNote, PsychologyLog, SessionRecap, LearningNote

class DailyJournalSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyJournal
        fields = "__all__"
        read_only_fields = ["user", "created_at", "updated_at"]

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