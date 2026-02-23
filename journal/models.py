import uuid
from django.db import models
from django.conf import settings

class DailyJournal(models.Model):
    """Daily reflection and streak tracking."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='daily_journals')
    
    SESSION_STATE_CHOICES = [
        ('green', 'Green'),
        ('yellow', 'Yellow'),
        ('red', 'Red'),
    ]
    LIMITS_FOLLOWED_CHOICES = [
        ('yes', 'Yes'),
        ('mostly', 'Mostly'),
        ('no', 'No'),
    ]

    journal_date = models.DateField()
    session_state = models.CharField(max_length=10, choices=SESSION_STATE_CHOICES, null=True, blank=True)
    prompt_text = models.TextField(blank=True)
    reflection = models.TextField(blank=True)
    intention_next_session = models.TextField(blank=True)
    limits_followed = models.CharField(max_length=10, choices=LIMITS_FOLLOWED_CHOICES, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'daily_journals'
        unique_together = ('user', 'journal_date') # Enforces 1 session per user per day
        ordering = ['-journal_date']

    def __str__(self):
        return f"Journal: {self.user.email} - {self.journal_date}"


class TradeNote(models.Model):
    """Per-trade qualitative notes."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='trade_notes')
    trade = models.ForeignKey('tradelog.Trade', on_delete=models.CASCADE, related_name='notes')
    
    note_text = models.TextField()
    tags = models.JSONField(default=list, blank=True) # e.g. ["#FOMO", "#breakout"]
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'trade_notes'
        ordering = ['-created_at']


class PsychologyLog(models.Model):
    """Deep dive into emotional state and confidence."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='psychology_logs')
    
    EMOTIONAL_STATE_CHOICES = [
        ('calm', 'Calm'),
        ('anxious', 'Anxious'),
        ('fomo', 'FOMO'),
        ('angry', 'Angry'),
        ('overconfident', 'Overconfident'),
        ('uncertain', 'Uncertain'),
    ]
    PRESSURE_SOURCE_CHOICES = [
        ('money', 'Money'),
        ('time', 'Time'),
        ('missed_move', 'Missed Move'),
        ('anger', 'Anger'),
        ('uncertainty', 'Uncertainty'),
    ]

    log_date = models.DateField()
    trade = models.ForeignKey('tradelog.Trade', on_delete=models.SET_NULL, null=True, blank=True, related_name='psych_logs')
    emotional_state = models.CharField(max_length=20, choices=EMOTIONAL_STATE_CHOICES)
    confidence_before = models.IntegerField(help_text="1-10 scale")
    satisfaction_after = models.IntegerField(help_text="1-10 scale")
    pressure_source = models.CharField(max_length=20, choices=PRESSURE_SOURCE_CHOICES, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'psychology_logs'
        ordering = ['-log_date', '-created_at']


class SessionRecap(models.Model):
    """Post-session review linked to the Discipline Guard."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='session_recaps')
    # session = models.ForeignKey('tradelog.DisciplineSession', on_delete=models.CASCADE, related_name='recaps') wiil implement
    
    OUTCOME_CHOICES = [
        ('good', 'Good'),
        ('neutral', 'Neutral'),
        ('bad', 'Bad'),
    ]

    recap_date = models.DateField()
    session_state = models.CharField(max_length=10, choices=DailyJournal.SESSION_STATE_CHOICES)
    outcome = models.CharField(max_length=10, choices=OUTCOME_CHOICES)
    
    what_went_right = models.JSONField(default=list, blank=True)
    what_slipped = models.JSONField(default=list, blank=True)
    rule_to_focus = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'session_recaps'
        ordering = ['-recap_date']


class LearningNote(models.Model):
    """Notes taken from the Learning Hub or external sources."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='learning_notes')
    
    LINKED_TYPE_CHOICES = [
        ('mistake', 'Mistake'),
        ('rule', 'Rule'),
        ('strategy', 'Strategy'),
        ('none', 'None'),
    ]

    lesson_source = models.CharField(max_length=255)
    key_takeaway = models.TextField()
    application_plan = models.TextField()
    
    linked_type = models.CharField(max_length=20, choices=LINKED_TYPE_CHOICES, default='none')
    linked_id = models.UUIDField(null=True, blank=True, help_text="ID of the related mistake, rule, or strategy")
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'learning_notes'
        ordering = ['-created_at']