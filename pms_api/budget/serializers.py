# Standard library imports

# Django imports

# Third-party imports
from rest_framework import serializers

# Local application imports
from pms_api.budget.models import BudgetForwardingStep
from pms_api.budget.models import BudgetRequest
from pms_api.core.serializers import BaseModelSerializer
from pms_api.lookups.models import Department


class BudgetForwardingStepSerializer(BaseModelSerializer):
    from_department_name = serializers.CharField(
        source="from_department.name_en",
        read_only=True,
    )
    to_department_name = serializers.CharField(
        source="to_department.name_en",
        read_only=True,
    )
    acted_by_email = serializers.SerializerMethodField()

    class Meta:
        model = BudgetForwardingStep
        fields = [
            "id",
            "uuid",
            "budget_request",
            "step_number",
            "action",
            "from_department",
            "from_department_name",
            "to_department",
            "to_department_name",
            "acted_by",
            "acted_by_email",
            "remarks",
            "created_at",
        ]
        read_only_fields = ["uuid", "created_at", "step_number"]

    def get_acted_by_email(self, obj) -> str | None:
        return obj.acted_by.email if obj.acted_by_id else None


class BudgetRequestListSerializer(BaseModelSerializer):
    project_code = serializers.CharField(source="project.code", read_only=True)
    project_title = serializers.CharField(source="project.title", read_only=True)
    department_name = serializers.CharField(
        source="current_department.name_en",
        read_only=True,
        default=None,
    )

    class Meta:
        model = BudgetRequest
        fields = [
            "id",
            "uuid",
            "project",
            "project_code",
            "project_title",
            "requested_amount",
            "approved_amount",
            "fiscal_year",
            "status",
            "current_department",
            "department_name",
            "created_at",
            "updated_at",
        ]


class BudgetRequestDetailSerializer(BaseModelSerializer):
    project_title = serializers.CharField(source="project.title", read_only=True)
    project_code = serializers.CharField(source="project.code", read_only=True)
    department_name = serializers.CharField(
        source="current_department.name_en",
        read_only=True,
        default=None,
    )
    forwarding_steps = BudgetForwardingStepSerializer(many=True, read_only=True)
    created_by_email = serializers.SerializerMethodField()

    class Meta:
        model = BudgetRequest
        fields = [
            "id",
            "uuid",
            "project",
            "project_code",
            "project_title",
            "requested_amount",
            "approved_amount",
            "fiscal_year",
            "justification",
            "status",
            "current_department",
            "department_name",
            "forwarding_steps",
            "created_at",
            "updated_at",
            "created_by_email",
        ]
        read_only_fields = [
            "uuid",
            "status",
            "approved_amount",
            "created_at",
            "updated_at",
        ]

    def get_created_by_email(self, obj) -> str | None:
        return obj.created_by.email if obj.created_by_id else None


class BudgetRequestCreateSerializer(BaseModelSerializer):
    class Meta:
        model = BudgetRequest
        fields = [
            "project",
            "requested_amount",
            "fiscal_year",
            "justification",
        ]

    def validate_project(self, project):
        if (
            BudgetRequest.objects.filter(project=project)
            .exclude(status="rejected")
            .exists()
        ):
            msg = "A budget request already exists for this project."
            raise serializers.ValidationError(msg)
        return project


class ForwardSerializer(serializers.Serializer):
    to_department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(),
    )
    remarks = serializers.CharField(required=False, allow_blank=True)


class ApproveSerializer(serializers.Serializer):
    approved_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    remarks = serializers.CharField(required=False, allow_blank=True)


class RejectSerializer(serializers.Serializer):
    remarks = serializers.CharField(required=True)
