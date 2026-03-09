import uuid
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    """Custom user manager where email is the unique identifier."""
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """Custom User model extended to match BitsOfTrade spec."""
    
    username = None
    email = models.EmailField(unique=True)
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    
    objects = UserManager()

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
        # Changed self.username to self.email
        return f"{self.email} ({self.subscription_type})"

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