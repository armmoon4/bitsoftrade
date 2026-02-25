import uuid
from django.db import models
from django.conf import settings


class DisciplineSession(models.Model):
    """One session per user per trading day. State escalates GREEN → YELLOW → RED."""

    SESSION_STATE_CHOICES = [
        ('green', 'Green'),
        ('yellow', 'Yellow'),
        ('red', 'Red'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='discipline_sessions')
    session_date = models.DateField()
    session_state = models.CharField(max_length=10, choices=SESSION_STATE_CHOICES, default='green')

    rules_violated = models.JSONField(default=list, blank=True)  # List of rule UUIDs
    violations_count = models.IntegerField(default=0)
    hard_violations = models.IntegerField(default=0)
    soft_violations = models.IntegerField(default=0)

    # Unlock flow
    required_actions_completed = models.BooleanField(default=False)
    cooldown_ends_at = models.DateTimeField(null=True, blank=True)
    journal_completed = models.BooleanField(default=False)
    trade_review_completed = models.BooleanField(default=False)
    unlocked_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'discipline_sessions'
        unique_together = ('user', 'session_date')
        ordering = ['-session_date']

    def __str__(self):
        return f"Session {self.user.username} {self.session_date} [{self.session_state.upper()}]"


class ViolationsLog(models.Model):
    """Per-violation log entry. Powers the violations timeline chart."""

    VIOLATION_TYPE_CHOICES = [
        ('hard', 'Hard'),
        ('soft', 'Soft'),
    ]
    SESSION_STATE_CHOICES = [
        ('green', 'Green'),
        ('yellow', 'Yellow'),
        ('red', 'Red'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='violations')
    session = models.ForeignKey(DisciplineSession, on_delete=models.CASCADE, related_name='violation_logs')
    trade = models.ForeignKey('tradelog.Trade', on_delete=models.SET_NULL, null=True, blank=True, related_name='violation_logs')
    rule = models.ForeignKey('rules.Rule', on_delete=models.CASCADE, related_name='violations')
    violation_type = models.CharField(max_length=10, choices=VIOLATION_TYPE_CHOICES)
    session_state_after = models.CharField(max_length=10, choices=SESSION_STATE_CHOICES)
    violated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'violations_log'
        ordering = ['-violated_at']

    def __str__(self):
        return f"Violation: {self.rule} [{self.violation_type}] on {self.violated_at.date()}"
