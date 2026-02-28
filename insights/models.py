import uuid
from django.db import models
from django.conf import settings


class UserMetricSnapshot(models.Model):
    """Cached snapshot of all 12 BitsOfTrade proprietary metrics per user."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='metric_snapshots')
    snapshot_date = models.DateField()

    # 1. Discipline Integrity Score — % GREEN sessions
    di_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    # 2. Violation Momentum Index — low/medium/high
    vmi_level = models.CharField(max_length=10, blank=True, null=True)
    # 3. Discipline Recovery Time — avg days RED/YELLOW → GREEN
    drt_days = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    # 4. Trade Permission Ratio — % trades in GREEN sessions
    tpr_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    # 5. Foregone Impact of Emotions — preventable losses INR
    fie_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    # 6. Obstinacy vs Resilience Score — 1-10
    ovr_score = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    # 7. Emotion Cost Index — INR cost of emotional trades
    eci_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    # 8. Confidence Accuracy Score — correlation confidence vs outcome
    cas_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    # 9. Disciplined Expectancy — avg R-multiple in GREEN sessions
    dae_r = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    # 10. Strategy Maturity Index
    smi_status = models.CharField(max_length=15, blank=True, null=True)
    # 11. Discipline Dependency Ratio — win rate delta GREEN vs non-GREEN
    ddr_level = models.CharField(max_length=10, blank=True, null=True)
    # 12. Capital Protection Index — % days within max daily loss rule
    cpi_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    calculated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_metric_snapshots'
        ordering = ['-snapshot_date']

    def __str__(self):
        return f"Metrics snapshot: {self.user.username} on {self.snapshot_date}"
