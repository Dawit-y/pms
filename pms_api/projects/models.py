from django.db import models

from pms_api.core.models.base import BaseModel
from pms_api.core.models.mixins import HistoryMixin


class Project(HistoryMixin, BaseModel):
    """
    A government project: road, school, hospital, dam, etc.
    All child data (employees, documents, payments...) hangs off this.

    History tracking enabled: All changes are automatically logged.
    Access via project.history.all()
    """

    code = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)

    project_type = models.ForeignKey(
        "lookups.Lookup",
        on_delete=models.PROTECT,
        related_name="projects",
        limit_choices_to={"lookup_type__code": "project_type"},
    )
    location = models.ForeignKey(
        "lookups.Location",
        on_delete=models.PROTECT,
        related_name="projects",
    )
    implementing_department = models.ForeignKey(
        "lookups.Department",
        on_delete=models.PROTECT,
        related_name="projects",
    )

    start_date = models.DateField(null=True, blank=True)
    planned_end_date = models.DateField(null=True, blank=True)
    actual_end_date = models.DateField(null=True, blank=True)

    total_budget = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
    )
    current_status = models.ForeignKey(
        "ProjectStatus",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    # Set True only after budget is approved
    is_active = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.code} — {self.title}"


class ProjectStatus(HistoryMixin, BaseModel):
    """
    One entry per status change. Changed only when monitoring team visits.

    History tracking enabled: Status changes are tracked for audit purposes.
    """

    STATUS_CHOICES = [
        ("registered", "Registered"),
        ("budget_requested", "Budget Requested"),
        ("budget_approved", "Budget Approved"),
        ("in_progress", "In Progress"),
        ("on_hold", "On Hold"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="status_history",
    )
    status = models.CharField(max_length=50, choices=STATUS_CHOICES)
    changed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="status_changes",
    )
    visit_date = models.DateField(null=True, blank=True)
    remarks = models.TextField(blank=True)
    physical_progress_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
    )
    financial_progress_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
    )

    class Meta:
        ordering = ["-created_at"]
