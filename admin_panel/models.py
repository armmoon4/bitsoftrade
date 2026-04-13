import uuid
from django.db import models
from django.contrib.auth.hashers import make_password, check_password


class Admin(models.Model):
    """Separate admin model, independent of Django's User model."""

    ACCESS_LEVEL_CHOICES = [
        ('super_admin', 'Super Admin'),
        ('admin', 'Admin'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    full_name = models.CharField(max_length=200)
    email = models.EmailField(unique=True)
    password_hash = models.CharField(max_length=500)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    access_level = models.CharField(max_length=15, choices=ACCESS_LEVEL_CHOICES, default='admin')
    profile_picture_url = models.CharField(max_length=500, blank=True, null=True)
    created_by_admin = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_admins'
    )
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'admins'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.full_name} ({self.access_level})"

    def set_password(self, raw_password):
        self.password_hash = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password_hash)

    @property
    def is_super_admin(self):
        return self.access_level == 'super_admin'


class AdminUserAction(models.Model):
    """Audit log for every admin action on a user account."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    admin = models.ForeignKey(Admin, on_delete=models.CASCADE, related_name='user_actions')
    target_user_id = models.UUIDField()
    action_type = models.CharField(
        max_length=50,
        help_text='toggle_active / delete / view_mistakes / view_profile'
    )
    action_detail = models.JSONField(null=True, blank=True)
    performed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'admin_user_actions'
        ordering = ['-performed_at']


class AdminAdminAction(models.Model):
    """Audit log for admin-on-admin actions (create/edit/delete)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    performed_by_admin = models.ForeignKey(Admin, on_delete=models.CASCADE, related_name='admin_actions_performed')
    target_admin = models.ForeignKey(Admin, on_delete=models.CASCADE, related_name='admin_actions_received')
    action_type = models.CharField(max_length=20, help_text='create / edit / delete')
    action_detail = models.JSONField(null=True, blank=True)
    performed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'admin_admin_actions'
        ordering = ['-performed_at']


# ─── CMS: User Reviews ────────────────────────────────────────────────────────

class Review(models.Model):
    """CMS-managed testimonial/review shown on the landing page."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reviewer_name = models.CharField(max_length=200)
    rating = models.PositiveSmallIntegerField(default=5, help_text='1–5 stars')
    review_text = models.TextField()
    is_visible = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0, help_text='Lower = shown first')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cms_reviews'
        ordering = ['display_order', '-created_at']

    def __str__(self):
        return f"{self.reviewer_name} ({'Shown' if self.is_visible else 'Hidden'})"


# ─── CMS: Pricing Plans ───────────────────────────────────────────────────────

class PricingPlan(models.Model):
    """CMS-managed subscription pricing plans."""

    BILLING_CYCLE_CHOICES = [
        ('forever', 'Forever (Free)'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('biannual', '6 Months'),
        ('annual', 'Annual'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)                          # e.g. "Free", "Pro", "Elite"
    price = models.DecimalField(max_digits=10, decimal_places=2)     # 0, 499, 2999 …
    billing_cycle = models.CharField(max_length=20, choices=BILLING_CYCLE_CHOICES, default='monthly')
    is_popular = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    features = models.JSONField(default=list, help_text='List of feature strings')
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cms_pricing_plans'
        ordering = ['display_order', 'price']

    def __str__(self):
        return f"{self.name} (₹{self.price}/{self.billing_cycle})"