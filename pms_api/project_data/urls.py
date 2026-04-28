from django.conf import settings
from django.urls import include
from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from pms_api.project_data.views import ContractorAssignmentViewSet
from pms_api.project_data.views import ContractorViewSet
from pms_api.project_data.views import EvaluationViewSet
from pms_api.project_data.views import IssueViewSet
from pms_api.project_data.views import MilestoneViewSet
from pms_api.project_data.views import MonitoringVisitViewSet
from pms_api.project_data.views import PaymentViewSet
from pms_api.project_data.views import ProcurementViewSet
from pms_api.project_data.views import ProjectDocumentViewSet
from pms_api.project_data.views import ProjectEmployeeViewSet
from pms_api.project_data.views import RiskViewSet

app_name = "project_data"

router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register(
    "project-employees",
    ProjectEmployeeViewSet,
    basename="project-employee",
)
router.register(
    "project-documents",
    ProjectDocumentViewSet,
    basename="project-document",
)
router.register("contractors", ContractorViewSet, basename="contractor")
router.register(
    "contractor-assignments",
    ContractorAssignmentViewSet,
    basename="contractor-assignment",
)
router.register("payments", PaymentViewSet, basename="payment")
router.register(
    "monitoring-visits",
    MonitoringVisitViewSet,
    basename="monitoring-visit",
)
router.register("evaluations", EvaluationViewSet, basename="evaluation")
router.register("risks", RiskViewSet, basename="risk")
router.register("milestones", MilestoneViewSet, basename="milestone")
router.register("issues", IssueViewSet, basename="issue")
router.register("procurements", ProcurementViewSet, basename="procurement")

urlpatterns = [path("", include(router.urls))]
