from django.contrib.auth import get_user_model
from django.db import models

from pms_api.core.models.base import BaseModel
from pms_api.core.models.notifications import notify

User = get_user_model()


class BudgetRequest(BaseModel):
    """
    Created after project profile is registered.
    Approval unlocks all child data on the project.
    """

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("submitted", "Submitted"),
        ("under_review", "Under Review"),
        ("forwarded", "Forwarded"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("revision_requested", "Revision Requested"),
    ]

    project = models.OneToOneField(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="budget_request",
    )
    requested_amount = models.DecimalField(max_digits=18, decimal_places=2)
    approved_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
    )
    fiscal_year = models.CharField(max_length=10)
    justification = models.TextField()
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default="draft",
        db_index=True,
    )
    current_department = models.ForeignKey(
        "lookups.Department",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pending_budget_requests",
    )

    def submit(self, submitted_by):
        self.status = "submitted"
        self.updated_by = submitted_by
        self.save()

    def approve(self, approved_by, approved_amount):
        self.status = "approved"
        self.approved_amount = approved_amount
        self.updated_by = approved_by
        self.save()
        # Unlock the project
        self.project.is_active = True
        self.project.save(update_fields=["is_active"])

    def reject(self, rejected_by, remarks=""):
        self.status = "rejected"
        self.updated_by = rejected_by
        self.save()

    class Meta:
        ordering = ["-created_at"]
        permissions = [
            ("submit_budgetrequest", "Can submit a budget request for review"),
            ("forward_budgetrequest", "Can forward a budget request to another department"),
            (
                "approve_budgetrequest",
                "Can approve, reject, or return a budget request for revision",
            ),
        ]


class BudgetForwardingStep(BaseModel):
    """
    Each row = one hop in the multi-department approval chain.
    Forwarding to a new dept notifies all users in that dept.
    """

    ACTIONS = [
        ("forwarded", "Forwarded"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("returned", "Returned"),
    ]

    budget_request = models.ForeignKey(
        BudgetRequest,
        on_delete=models.CASCADE,
        related_name="forwarding_steps",
    )
    from_department = models.ForeignKey(
        "lookups.Department",
        on_delete=models.PROTECT,
        related_name="forwarded_from_steps",
    )
    to_department = models.ForeignKey(
        "lookups.Department",
        on_delete=models.PROTECT,
        related_name="forwarded_to_steps",
    )
    action = models.CharField(max_length=20, choices=ACTIONS)
    acted_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="forwarding_actions",
    )
    remarks = models.TextField(blank=True)
    step_number = models.PositiveSmallIntegerField()

    class Meta:
        pass

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.action == "forwarded":
            self._notify_target_department()

    def _notify_target_department(self):
        """Notify all users in to_department when a request is forwarded to them."""

        dept_users = User.objects.filter(department=self.to_department, is_active=True)
        for user in dept_users:
            notify(
                recipient=user,
                verb=f"A budget request for '{self.budget_request.project.title}'"
                f" has been forwarded to your department",
                action_object=self.budget_request,
                actor=self.acted_by,
            )
