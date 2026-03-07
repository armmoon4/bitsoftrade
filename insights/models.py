import uuid
from django.db import models
from django.conf import settings


class UserMetricSnapshot(models.Model):
    """Cached snapshot of all 12 BitsOfTrade proprietary metrics per user."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='metric_snapshots')
    snapshot_date = models.DateField()

    # 1. Discipline Integrity Score (DIS™) — 0-100 weighted score
    di_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # 2. Violation Momentum Index (VMI) — numeric 0-100 AND text level
    vmi_score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    vmi_level = models.CharField(max_length=10, blank=True, null=True)   # Low / Medium / High

    # 3. Discipline Recovery Time (DRT) — avg sessions to recover
    drt_days = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # 4. Trading Permission Ratio (TPR) — % of sessions that were GREEN
    tpr_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # 5. Forced Inactivity Effectiveness (FIE) — estimated INR saved
    fie_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    # 6. Override Resistance Score (OVR) — 1-10
    ovr_score = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)

    # 7. Emotion Cost Index (ECI) — INR cost of emotional trades (negative = loss)
    eci_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    # 8. Confidence Accuracy Score (CAS) — 0-100%
    cas_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # 9. Discipline-Adjusted Expectancy (DAE) — disciplined avg P&L and raw avg P&L
    dae_r = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)    # disciplined
    dae_raw = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)  # raw (all trades)

    # 10. Strategy Maturity Index (SMI) — numeric 0-100 score AND status string
    smi_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    smi_status = models.CharField(max_length=15, blank=True, null=True)

    # 11. Discipline Dependency Ratio (DDR) — numeric % AND level
    ddr_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    ddr_level = models.CharField(max_length=10, blank=True, null=True)

    # 12. Capital Protection Index (CPI) — % days within max-loss rule
    cpi_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    calculated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_metric_snapshots'
        ordering = ['-snapshot_date']

    def __str__(self):
        return f"Metrics snapshot: {self.user.username} on {self.snapshot_date}"
