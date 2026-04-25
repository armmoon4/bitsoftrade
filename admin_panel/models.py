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
    """
    CMS-managed pricing plans for fixed frontend cards.

    card_key ties each DB row to a specific hardcoded frontend card.
    The four keys that match your current UI:

        discipline_tools   → "Discipline Tools" card  (monthly + yearly toggle)
        learning_hub       → "Learning Hub" card       (6-month, single price)
        combo_monthly      → "Complete System – Monthly Combo" card
        combo_annual       → "Complete System – Annual Combo" card

    price        = the primary / monthly price shown on the card
    price_yearly = yearly price (only used when card_key = 'discipline_tools')
                   NULL on all other cards.
    """

    CARD_KEY_CHOICES = [
        ('discipline_tools', 'Discipline Tools (monthly/yearly toggle)'),
        ('learning_hub',     'Learning Hub (6-month)'),
        ('combo_monthly',    'Complete System – Monthly Combo'),
        ('combo_annual',     'Complete System – Annual Combo'),
    ]

    BILLING_CYCLE_CHOICES = [
        ('forever',   'Forever (Free)'),
        ('monthly',   'Monthly'),
        ('quarterly', 'Quarterly'),
        ('biannual',  '6 Months'),
        ('annual',    'Annual'),
    ]

    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # ── Which frontend card does this row control? ────────────────────────────
    card_key = models.CharField(
    max_length=30,
    choices=CARD_KEY_CHOICES,
    unique=True,
    default='discipline_tools',
    help_text='Fixed identifier that the frontend uses to find this card.',
    )

    # ── Display copy ──────────────────────────────────────────────────────────
    name         = models.CharField(max_length=100, help_text='Card heading, e.g. "Discipline Tools"')
    tagline      = models.CharField(
        max_length=300, blank=True, default='',
        help_text='Short subtitle shown under the heading, e.g. "Traders who want to control activity…"',
    )
    badge        = models.CharField(
        max_length=100, blank=True, default='',
        help_text='Small badge/label on the card, e.g. "Behavior Control & Prevention"',
    )
    cta_label    = models.CharField(
        max_length=100, blank=True, default='',
        help_text='Button label, e.g. "Activate Discipline Tools"',
    )
    footer_note  = models.CharField(
        max_length=300, blank=True, default='',
        help_text='Small grey text under the button, e.g. "Discipline infrastructure only."',
    )

    # ── Pricing ───────────────────────────────────────────────────────────────
    price        = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text='Primary price (monthly price for discipline_tools, flat price for others).',
    )
    price_yearly = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='Yearly price — only relevant for discipline_tools card. Leave NULL for others.',
    )
    billing_cycle = models.CharField(
        max_length=20, choices=BILLING_CYCLE_CHOICES, default='monthly',
        help_text='Billing cycle label shown on the card.',
    )

    # ── Feature bullets ───────────────────────────────────────────────────────
    features     = models.JSONField(
        default=list,
        help_text='Ordered list of feature strings shown as bullet points on the card.',
    )

    # ── Visibility / ordering ─────────────────────────────────────────────────
    is_popular   = models.BooleanField(default=False)
    is_active    = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cms_pricing_plans'
        ordering = ['display_order', 'price']

    def __str__(self):
        return f"{self.name} [{self.card_key}]"


# ─── CMS: Learning Hub ────────────────────────────────────────────────────────

class LearningModule(models.Model):
    """
    CMS-managed top-level module shown on the Learning Hub page.
    e.g. 'MODULE 1: CORE INTRODUCTION', 'Market Basics & Foundations'
    """

    id            = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title         = models.CharField(max_length=300)
    subtitle      = models.CharField(max_length=300, blank=True, default='',
                                     help_text='Optional short description shown under the title')
    display_order = models.PositiveIntegerField(default=0, help_text='Lower = shown first')
    is_visible    = models.BooleanField(default=True)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cms_learning_modules'
        ordering = ['display_order', 'created_at']

    def __str__(self):
        return f"{self.title} ({'Shown' if self.is_visible else 'Hidden'})"


class LearningTopic(models.Model):
    """
    CMS-managed individual topic/bullet point inside a LearningModule.
    e.g. 'Understanding the Stock Market', 'Why Focus on Price Action'
    """

    id            = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    module        = models.ForeignKey(
        LearningModule, on_delete=models.CASCADE, related_name='topics'
    )
    title         = models.CharField(max_length=300)
    display_order = models.PositiveIntegerField(default=0, help_text='Order within the module')
    is_visible    = models.BooleanField(default=True)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cms_learning_topics'
        ordering = ['display_order', 'created_at']

    def __str__(self):
        return f"{self.module.title} → {self.title}"