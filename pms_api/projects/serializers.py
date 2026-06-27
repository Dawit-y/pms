from rest_framework import serializers

from pms_api.core.serializers import BaseModelSerializer
from pms_api.projects.models import Project
from pms_api.projects.models import ProjectStatus
from pms_api.projects.models import ProjectTag


class ProjectTagSerializer(BaseModelSerializer):
    class Meta:
        model = ProjectTag
        fields = [
            "id",
            "uuid",
            "name",
            "color",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "uuid",
            "created_at",
            "updated_at",
        ]


class ProjectStatusSerializer(BaseModelSerializer):
    changed_by_email = serializers.SerializerMethodField()

    class Meta:
        model = ProjectStatus
        fields = [
            "id",
            "uuid",
            "project",
            "status",
            "changed_by",
            "changed_by_email",
            "visit_date",
            "remarks",
            "physical_progress_pct",
            "financial_progress_pct",
            "created_at",
        ]
        read_only_fields = ["uuid", "created_at"]

    def get_changed_by_email(self, obj) -> str | None:
        return obj.changed_by.email if obj.changed_by_id else None


class ProjectListSerializer(BaseModelSerializer):
    """Lightweight: for list views."""

    current_status_label = serializers.CharField(
        source="current_status.status",
        read_only=True,
        default=None,
    )
    location_name = serializers.CharField(
        source="location.name_en",
        read_only=True,
        default=None,
    )
    department_name = serializers.CharField(
        source="implementing_department.name_en",
        read_only=True,
        default=None,
    )
    project_type_name = serializers.CharField(
        source="project_type.name_en",
        read_only=True,
        default=None,
    )
    budget_status = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            "id",
            "uuid",
            "code",
            "title",
            "description",
            "project_type",
            "project_type_name",
            "location",
            "location_name",
            "implementing_department",
            "department_name",
            "start_date",
            "planned_end_date",
            "total_budget",
            "current_status",
            "current_status_label",
            "is_active",
            "budget_status",
            "created_at",
        ]

    def get_budget_status(self, obj) -> str | None:
        try:
            return obj.budget_request.status
        except Exception:  # noqa: BLE001
            return None


class ProjectDetailSerializer(BaseModelSerializer):
    """Full detail with nested status history and budget summary."""

    current_status_detail = ProjectStatusSerializer(
        source="current_status",
        read_only=True,
    )
    location_name = serializers.CharField(
        source="location.name_en",
        read_only=True,
        default=None,
    )
    location_path = serializers.SerializerMethodField()
    department_name = serializers.CharField(
        source="implementing_department.name_en",
        read_only=True,
        default=None,
    )
    project_type_name = serializers.CharField(
        source="project_type.name_en",
        read_only=True,
        default=None,
    )
    # Expose tags in ProjectDetailSerializer
    tags = ProjectTagSerializer(
        many=True,
        read_only=True,
    )
    budget_summary = serializers.SerializerMethodField()
    recent_status_history = serializers.SerializerMethodField()
    completion_pct = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            "id",
            "uuid",
            "code",
            "title",
            "description",
            "project_type",
            "project_type_name",
            "location",
            "location_name",
            "location_path",
            "implementing_department",
            "department_name",
            "start_date",
            "planned_end_date",
            "actual_end_date",
            "total_budget",
            "current_status",
            "current_status_detail",
            "tags",
            "is_active",
            "budget_summary",
            "recent_status_history",
            "completion_pct",
            "created_at",
            "updated_at",
            "created_by_email",
            "updated_by_email",
        ]
        read_only_fields = [
            "uuid",
            "is_active",
            "current_status",
            "created_at",
            "updated_at",
        ]

    def get_location_path(self, obj) -> str | None:
        if not obj.location_id:
            return None
        ancestors = obj.location.get_ancestors(include_self=True)
        return " > ".join(a.name_en for a in ancestors)

    def get_budget_summary(self, obj) -> dict | None:
        try:
            br = obj.budget_request
            return {
                "uuid": str(br.uuid),
                "status": br.status,
                "requested_amount": str(br.requested_amount),
                "approved_amount": str(br.approved_amount) if br.approved_amount else None,
                "fiscal_year": br.fiscal_year,
            }
        except Exception:  # noqa: BLE001
            return None

    def get_recent_status_history(self, obj) -> list:
        # `status_history` is prefetched ordered by -created_at with changed_by
        # joined; slicing the prefetched list avoids re-querying.
        history = list(obj.status_history.all())[:5]
        return ProjectStatusSerializer(history, many=True).data

    def get_completion_pct(self, obj) -> float | None:
        history = list(obj.status_history.all())
        if history:
            return float(history[0].physical_progress_pct)
        return None


class ProjectCreateSerializer(BaseModelSerializer):
    tags = serializers.PrimaryKeyRelatedField(
        queryset=ProjectTag.objects.all(),
        many=True,
        required=False,
    )

    class Meta:
        model = Project
        fields = [
            "uuid",
            "code",
            "title",
            "description",
            "project_type",
            "location",
            "tags",
            "implementing_department",
            "start_date",
            "planned_end_date",
            "total_budget",
        ]
        read_only_fields = ["uuid"]

    def validate_code(self, value):
        if Project.objects.filter(code=value).exists():
            msg = f"Project code '{value}' already exists."
            raise serializers.ValidationError(msg)
        return value

    def create(self, validated_data):
        tags = validated_data.pop("tags", [])
        instance = super().create(validated_data)

        if tags:
            instance.tags.set(tags)
        # Auto-create first status entry
        user = self.context["request"].user
        ps = ProjectStatus.objects.create(
            project=instance,
            status="registered",
            changed_by=user,
            created_by=user,
            updated_by=user,
        )
        instance.current_status = ps
        instance.save(update_fields=["current_status"])
        return instance


class ProjectStatusCreateSerializer(BaseModelSerializer):
    class Meta:
        model = ProjectStatus
        fields = [
            "project",
            "status",
            "visit_date",
            "remarks",
            "physical_progress_pct",
            "financial_progress_pct",
        ]

    def create(self, validated_data):
        user = self.context["request"].user
        validated_data["changed_by"] = user
        instance = super().create(validated_data)
        # Update project's current status pointer
        instance.project.current_status = instance
        instance.project.save(update_fields=["current_status"])
        return instance
