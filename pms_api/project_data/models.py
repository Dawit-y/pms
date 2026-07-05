from django.db import models
from django.utils import timezone

from pms_api.core.models.base import BaseModel
from pms_api.projects.models import ProjectStatus


# ── Guard mixin ─────────────────────────────────────────────────────────────
class ProjectDataMixin(models.Model):
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="%(class)s_set",
    )

    class Meta:
        abstract = True

    @property
    def is_editable(self):
        return self.project.is_active


# ── Employee ─────────────────────────────────────────────────────────────────
class ProjectEmployee(ProjectDataMixin, BaseModel):
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="project_assignments",
    )
    role_on_project = models.ForeignKey(
        "lookups.Lookup",
        on_delete=models.PROTECT,
        limit_choices_to={"lookup_type__code": "employee_role"},
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    daily_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    is_current = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user} - {self.project}"


# ── Document ─────────────────────────────────────────────────────────────────
class ProjectDocument(ProjectDataMixin, BaseModel):
    title = models.CharField(max_length=500)
    document_type = models.ForeignKey(
        "lookups.Lookup",
        on_delete=models.PROTECT,
        limit_choices_to={"lookup_type__code": "document_type"},
    )
    file = models.FileField(upload_to="projects/documents/%Y/%m/")
    version = models.CharField(max_length=20, default="1.0")
    is_confidential = models.BooleanField(default=False)
    expiry_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return self.title


# ── Contractor ───────────────────────────────────────────────────────────────
class Contractor(BaseModel):
    name = models.CharField(max_length=500)
    registration_number = models.CharField(max_length=100, unique=True)
    contractor_type = models.ForeignKey(
        "lookups.Lookup",
        on_delete=models.PROTECT,
        limit_choices_to={"lookup_type__code": "contractor_type"},
    )
    tin_number = models.CharField(max_length=50, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    is_blacklisted = models.BooleanField(default=False)
    blacklist_reason = models.TextField(blank=True)

    class Meta:
        permissions = [
            ("blacklist_contractor", "Can blacklist or unblacklist a contractor"),
        ]

    def __str__(self):
        return self.name


class ContractorAssignment(ProjectDataMixin, BaseModel):
    contractor = models.ForeignKey(
        Contractor,
        on_delete=models.PROTECT,
        related_name="assignments",
    )
    contract_number = models.CharField(max_length=100, unique=True)
    contract_amount = models.DecimalField(max_digits=18, decimal_places=2)
    contract_start = models.DateField()
    contract_end = models.DateField()
    scope_of_work = models.TextField()
    status = models.ForeignKey(
        "lookups.Lookup",
        on_delete=models.PROTECT,
        limit_choices_to={"lookup_type__code": "contract_status"},
    )

    def __str__(self):
        return self.contract_number


# ── Payment ───────────────────────────────────────────────────────────────────
class Payment(ProjectDataMixin, BaseModel):
    PAYMENT_TYPES = [
        ("advance", "Advance"),
        ("progress", "Progress"),
        ("final", "Final"),
        ("retention", "Retention"),
    ]

    contractor_assignment = models.ForeignKey(
        ContractorAssignment,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPES)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    payment_date = models.DateField()
    reference_number = models.CharField(max_length=100, unique=True)
    bank_reference = models.CharField(max_length=100, blank=True)
    is_approved = models.BooleanField(default=False)

    approved_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_payments",
    )

    class Meta:
        permissions = [
            ("approve_payment", "Can approve a contractor payment"),
        ]

    def __str__(self):
        return self.reference_number


# ── Monitoring ────────────────────────────────────────────────────────────────
class MonitoringVisit(ProjectDataMixin, BaseModel):
    visit_date = models.DateField()
    visit_team = models.ManyToManyField(
        "accounts.User",
        related_name="monitoring_visits",
    )
    physical_progress_pct = models.DecimalField(max_digits=5, decimal_places=2)
    financial_progress_pct = models.DecimalField(max_digits=5, decimal_places=2)
    findings = models.TextField()
    recommendations = models.TextField(blank=True)
    next_visit_date = models.DateField(null=True, blank=True)
    status_changed_to = models.CharField(max_length=50, blank=True)

    def __str__(self):
        return f"Visit {self.project} - {self.visit_date}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        if self.status_changed_to:
            ProjectStatus.objects.create(
                project=self.project,
                status=self.status_changed_to,
                changed_by=self.updated_by or self.created_by,
                visit_date=self.visit_date,
                physical_progress_pct=self.physical_progress_pct,
                financial_progress_pct=self.financial_progress_pct,
            )


# ── Evaluation ────────────────────────────────────────────────────────────────
class Evaluation(ProjectDataMixin, BaseModel):
    EVAL_TYPES = [
        ("mid_term", "Mid-Term"),
        ("final", "Final"),
        ("ex_ante", "Ex-Ante"),
        ("ex_post", "Ex-Post"),
    ]

    evaluation_type = models.CharField(max_length=20, choices=EVAL_TYPES)
    evaluator = models.ForeignKey("accounts.User", on_delete=models.PROTECT)
    evaluation_date = models.DateField()
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    summary = models.TextField()

    def __str__(self):
        return f"{self.evaluation_type} - {self.project}"


# ── Risk ──────────────────────────────────────────────────────────────────────
class Risk(ProjectDataMixin, BaseModel):
    PROBABILITY = [("low", "Low"), ("medium", "Medium"), ("high", "High")]
    IMPACT = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("critical", "Critical"),
    ]
    SCORE_WEIGHTS = {
        "low": 1,
        "medium": 2,
        "high": 3,
        "critical": 4,
    }

    title = models.CharField(max_length=500)
    description = models.TextField()
    probability = models.CharField(max_length=10, choices=PROBABILITY)
    impact = models.CharField(max_length=10, choices=IMPACT)
    mitigation_plan = models.TextField(blank=True)
    risk_owner = models.ForeignKey("accounts.User", on_delete=models.PROTECT)
    is_resolved = models.BooleanField(default=False)

    def __str__(self):
        return self.title

    @property
    def score(self):
        return self.SCORE_WEIGHTS[self.probability] * self.SCORE_WEIGHTS[self.impact]


# ── Milestone ─────────────────────────────────────────────────────────────────
class Milestone(ProjectDataMixin, BaseModel):
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    planned_date = models.DateField()
    actual_date = models.DateField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    completion_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    def __str__(self):
        return self.title

    @property
    def is_overdue(self):
        return not self.is_completed and self.planned_date < timezone.localdate()


# ── Issue ─────────────────────────────────────────────────────────────────────
class Issue(ProjectDataMixin, BaseModel):
    SEVERITY = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("blocker", "Blocker"),
    ]

    title = models.CharField(max_length=500)
    description = models.TextField()
    severity = models.CharField(max_length=10, choices=SEVERITY)
    assigned_to = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    due_date = models.DateField(null=True, blank=True)
    is_resolved = models.BooleanField(default=False)

    def __str__(self):
        return self.title

    @property
    def is_overdue(self):
        return (
            self.due_date is not None
            and not self.is_resolved
            and self.due_date < timezone.localdate()
        )


# ── IssueComment ──────────────────────────────────────────────────────────────
class IssueComment(BaseModel):
    issue = models.ForeignKey(
        "Issue",
        on_delete=models.CASCADE,
        related_name="comments",
    )
    body = models.TextField()

    def __str__(self):
        return self.body[:50]


# ── Procurement ──────────────────────────────────────────────────────────────
class Procurement(ProjectDataMixin, BaseModel):
    METHOD_CHOICES = [
        ("open_bid", "Open Bid"),
        ("restricted_bid", "Restricted Bid"),
        ("direct", "Direct"),
        ("framework", "Framework Agreement"),
    ]

    item_description = models.CharField(max_length=500)
    procurement_method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    estimated_cost = models.DecimalField(max_digits=18, decimal_places=2)
    actual_cost = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
    )
    tender_date = models.DateField(null=True, blank=True)
    award_date = models.DateField(null=True, blank=True)
    status = models.ForeignKey(
        "lookups.Lookup",
        on_delete=models.PROTECT,
        limit_choices_to={"lookup_type__code": "procurement_status"},
    )

    def __str__(self):
        return self.item_description
