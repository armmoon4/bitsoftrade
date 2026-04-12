import uuid
from django.db import models
from django.conf import settings


class Notification(models.Model):
    """
    Stores in-app notifications for users.
    Created automatically by the rule engine whenever a rule is triggered
    or violated, and optionally when a session state changes.
    """

    NOTIFICATION_TYPE_CHOICES = [
        ('rule_triggered', 'Rule Triggered'),
        ('rule_violated', 'Rule Violated'),
        ('session_locked', 'Session Locked'),
        ('session_unlocked', 'Session Unlocked'),
    ]

    SEVERITY_CHOICES = [
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('error', 'Error'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )

    notification_type = models.CharField(
        max_length=30,
        choices=NOTIFICATION_TYPE_CHOICES,
        db_index=True,
    )

    # 'info' for soft/warn rules, 'warning' for yellow session,
    # 'error' for hard/lock rules and red session.
    severity = models.CharField(
        max_length=10,
        choices=SEVERITY_CHOICES,
        default='info',
    )

    title = models.CharField(max_length=255)
    message = models.TextField()

    # Optional FK links for traceability
    rule = models.ForeignKey(
        'rules.Rule',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications',
    )
    session = models.ForeignKey(
        'discipline.DisciplineSession',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications',
    )
    trade = models.ForeignKey(
        'tradelog.Trade',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications',
    )

    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.severity.upper()}] {self.title} → {self.user.username}"
