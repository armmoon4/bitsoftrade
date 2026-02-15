from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom User model with role-based access control"""
    
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('user', 'User'),
    ]
    
    SUBSCRIPTION_CHOICES = [
        ('freebie', 'Freebie'),
        ('premium', 'Premium'),
        ('pro', 'Pro'),
    ]
    
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='user')
    subscription_type = models.CharField(
        max_length=10, 
        choices=SUBSCRIPTION_CHOICES, 
        default='freebie'
    )
    phone = models.CharField(max_length=20, blank=True, null=True)
    profile_picture = models.ImageField(
        upload_to='profiles/', 
        blank=True, 
        null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'users'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.username} ({self.role})"
    
    @property
    def is_admin(self):
        return self.role == 'admin'
    
    @property
    def is_premium(self):
        return self.subscription_type == 'premium'
