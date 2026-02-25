import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom User model extended to match BitsOfTrade spec."""

    SUBSCRIPTION_TYPE_CHOICES = [
        ('none', 'None'),
        ('tool', 'Tool Plan (Pro)'),
        ('learning', 'Learning Plan'),
        ('both', 'Tool + Learning'),
    ]

    SUBSCRIPTION_STATUS_CHOICES = [
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]

    # Profile
    profile_picture = models.ImageField(upload_to='profiles/', blank=True, null=True)

    # Capital (required for % based rules)
    trading_capital = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    # Subscription
    subscription_type = models.CharField(
        max_length=10, choices=SUBSCRIPTION_TYPE_CHOICES, default='none'
    )
    subscription_status = models.CharField(
        max_length=15, choices=SUBSCRIPTION_STATUS_CHOICES, default='active'
    )
    subscription_start = models.DateTimeField(null=True, blank=True)
    subscription_end = models.DateTimeField(null=True, blank=True)
    razorpay_customer_id = models.CharField(max_length=100, blank=True, null=True)

    # Journal streaks
    current_streak = models.IntegerField(default=0)
    longest_streak = models.IntegerField(default=0)

    # Admin controls
    is_active = models.BooleanField(default=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'users'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.username} ({self.subscription_type})"

    @property
    def has_tool_access(self):
        from django.utils import timezone
        return (
            self.subscription_type in ('tool', 'both')
            and self.subscription_status == 'active'
            and (self.subscription_end is None or self.subscription_end > timezone.now())
        )

    @property
    def has_learning_access(self):
        from django.utils import timezone
        return (
            self.subscription_type in ('learning', 'both')
            and self.subscription_status == 'active'
            and (self.subscription_end is None or self.subscription_end > timezone.now())
        )
