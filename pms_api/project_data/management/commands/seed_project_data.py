"""
Seed the per-project child entities: Contractors, ContractorAssignments,
Payments, Milestones, Risks, Issues, Procurements, ProjectEmployees,
MonitoringVisits, and Evaluations.

Requires `seed_lookups` and `seed_projects` to have been run first.
ProjectDocument is intentionally skipped — it expects a real uploaded file.

Usage:
    uv run python manage.py seed_project_data --count 40
    uv run python manage.py seed_project_data --count 100 --flush
"""
# ruff: noqa: PLR2004

from __future__ import annotations

import datetime as dt
import random
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.db import transaction
from faker import Faker

from pms_api.lookups.models import Lookup
from pms_api.project_data.models import Contractor
from pms_api.project_data.models import ContractorAssignment
from pms_api.project_data.models import Evaluation
from pms_api.project_data.models import Issue
from pms_api.project_data.models import Milestone
from pms_api.project_data.models import MonitoringVisit
from pms_api.project_data.models import Payment
from pms_api.project_data.models import Procurement
from pms_api.project_data.models import ProjectEmployee
from pms_api.project_data.models import Risk
from pms_api.projects.models import Project

User = get_user_model()

PAYMENT_TYPES = [c[0] for c in Payment.PAYMENT_TYPES]
EVAL_TYPES = [c[0] for c in Evaluation.EVAL_TYPES]
SEVERITIES = [c[0] for c in Issue.SEVERITY]
PROBABILITIES = [c[0] for c in Risk.PROBABILITY]
IMPACTS = [c[0] for c in Risk.IMPACT]
PROCUREMENT_METHODS = [c[0] for c in Procurement.METHOD_CHOICES]


class Command(BaseCommand):
    help = (
        "Seed per-project child data: contractors, assignments, payments, "
        "milestones, risks, issues, procurements, employees, monitoring visits, "
        "and evaluations."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=20,
            help="Number of contractors to create (default: 20). Per-project child "
            "rows are generated independently for every existing project.",
        )
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Hard-delete existing project_data rows before seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        count: int = options["count"]
        flush: bool = options["flush"]

        if count <= 0:
            msg = "--count must be a positive integer"
            raise CommandError(msg)

        contractor_types = list(Lookup.objects.filter(lookup_type__code="contractor_type"))
        contract_statuses = list(Lookup.objects.filter(lookup_type__code="contract_status"))
        procurement_statuses = list(Lookup.objects.filter(lookup_type__code="procurement_status"))
        employee_roles = list(Lookup.objects.filter(lookup_type__code="employee_role"))
        projects = list(Project.objects.all())
        users = list(User.objects.all())

        if (
            not contractor_types
            or not contract_statuses
            or not procurement_statuses
            or not employee_roles
        ):
            msg = "Missing required lookups. Run `seed_lookups` first."
            raise CommandError(msg)
        if not projects:
            msg = "No projects found. Run `seed_projects` first."
            raise CommandError(msg)
        if not users:
            msg = "No users found. Create at least one user first."
            raise CommandError(msg)

        if flush:
            self.stdout.write(self.style.WARNING("Flushing project_data rows..."))
            Payment.all_objects.all().delete()
            ContractorAssignment.all_objects.all().delete()
            Contractor.all_objects.all().delete()
            Milestone.all_objects.all().delete()
            Risk.all_objects.all().delete()
            Issue.all_objects.all().delete()
            Procurement.all_objects.all().delete()
            ProjectEmployee.all_objects.all().delete()
            MonitoringVisit.all_objects.all().delete()
            Evaluation.all_objects.all().delete()

        fake = Faker()
        contractors = self._seed_contractors(fake, count, contractor_types)

        stats = {
            "assignments": 0,
            "payments": 0,
            "milestones": 0,
            "risks": 0,
            "issues": 0,
            "procurements": 0,
            "employees": 0,
            "visits": 0,
            "evaluations": 0,
        }

        for project in projects:
            stats["assignments"] += self._seed_assignments_and_payments(
                fake,
                project,
                contractors,
                contract_statuses,
                users,
            )
            stats["payments"] += self._payment_count_for_project(project)
            stats["milestones"] += self._seed_milestones(fake, project)
            stats["risks"] += self._seed_risks(fake, project, users)
            stats["issues"] += self._seed_issues(fake, project, users)
            stats["procurements"] += self._seed_procurements(fake, project, procurement_statuses)
            stats["employees"] += self._seed_employees(fake, project, users, employee_roles)
            stats["visits"] += self._seed_visits(fake, project, users)
            stats["evaluations"] += self._seed_evaluations(fake, project, users)

        self.stdout.write(self.style.SUCCESS("OK:Project data seeded:"))
        for key, value in stats.items():
            self.stdout.write(f"  {key}: {value}")

    # ── Contractors ────────────────────────────────────────────────────────
    def _seed_contractors(
        self,
        fake: Faker,
        count: int,
        contractor_types: list,
    ) -> list[Contractor]:
        existing = Contractor.all_objects.count()
        created: list[Contractor] = list(Contractor.objects.all())
        for i in range(count):
            seq = existing + i + 1
            reg = f"REG-{seq:06d}"
            if Contractor.all_objects.filter(registration_number=reg).exists():
                continue
            contractor = Contractor.objects.create(
                name=f"{fake.last_name()} {fake.company_suffix()} Construction PLC",
                registration_number=reg,
                contractor_type=random.choice(contractor_types),  # noqa: S311
                tin_number=fake.numerify("##########"),
                phone=fake.phone_number()[:20],
                email=fake.company_email(),
                address=fake.address(),
                is_blacklisted=False,
            )
            created.append(contractor)
        self.stdout.write(f"  Contractors: {len(created)} total in DB.")
        return created

    # ── Assignments + Payments ─────────────────────────────────────────────
    def _seed_assignments_and_payments(
        self,
        fake: Faker,
        project: Project,
        contractors: list[Contractor],
        contract_statuses: list[Lookup],
        users: list,
    ) -> int:
        if not contractors:
            return 0
        n = random.randint(1, 3)  # noqa: S311
        created = 0
        for _ in range(n):
            contract_number = f"C-{project.code}-{fake.unique.numerify('######')}"
            if ContractorAssignment.all_objects.filter(contract_number=contract_number).exists():
                continue
            start = project.start_date or fake.date_between(start_date="-2y", end_date="-90d")
            end = start + dt.timedelta(days=random.randint(180, 900))  # noqa: S311
            amount = Decimal(random.randint(100_000, 20_000_000)).quantize(Decimal("1.00"))  # noqa: S311
            assignment = ContractorAssignment.objects.create(
                project=project,
                contractor=random.choice(contractors),  # noqa: S311
                contract_number=contract_number,
                contract_amount=amount,
                contract_start=start,
                contract_end=end,
                scope_of_work=fake.paragraph(nb_sentences=3),
                status=random.choice(contract_statuses),  # noqa: S311
            )
            created += 1
            self._seed_payments(fake, project, assignment, users)
        return created

    def _seed_payments(
        self,
        fake: Faker,
        project: Project,
        assignment: ContractorAssignment,
        users: list,
    ) -> int:
        n = random.randint(1, 4)  # noqa: S311
        created = 0
        for _ in range(n):
            ref = f"PAY-{fake.unique.numerify('########')}"
            if Payment.all_objects.filter(reference_number=ref).exists():
                continue
            approved = random.random() < 0.7  # noqa: S311
            Payment.objects.create(
                project=project,
                contractor_assignment=assignment,
                payment_type=random.choice(PAYMENT_TYPES),  # noqa: S311
                amount=Decimal(
                    random.randint(10_000, int(assignment.contract_amount / 4)),  # noqa: S311
                ).quantize(Decimal("1.00")),
                payment_date=fake.date_between(
                    start_date=assignment.contract_start,
                    end_date=assignment.contract_end,
                ),
                reference_number=ref,
                bank_reference=fake.bothify("BNK-####-????"),
                is_approved=approved,
                approved_by=random.choice(users) if approved else None,  # noqa: S311
            )
            created += 1
        return created

    def _payment_count_for_project(self, project: Project) -> int:
        return Payment.objects.filter(project=project).count()

    # ── Milestones ─────────────────────────────────────────────────────────
    def _seed_milestones(self, fake: Faker, project: Project) -> int:
        n = random.randint(1, 4)  # noqa: S311
        for _ in range(n):
            planned = (project.start_date or fake.date_between(start_date="-1y")) + dt.timedelta(
                days=random.randint(30, 720),  # noqa: S311
            )
            is_complete = random.random() < 0.4  # noqa: S311
            actual_date = None
            if is_complete:
                actual_date = planned + dt.timedelta(days=random.randint(-15, 60))  # noqa: S311
            pct_value = 100 if is_complete else random.randint(0, 90)  # noqa: S311
            Milestone.objects.create(
                project=project,
                title=fake.sentence(nb_words=4).rstrip("."),
                description=fake.paragraph(nb_sentences=2),
                planned_date=planned,
                actual_date=actual_date,
                is_completed=is_complete,
                completion_pct=Decimal(pct_value).quantize(Decimal("0.01")),
            )
        return n

    # ── Risks ──────────────────────────────────────────────────────────────
    def _seed_risks(self, fake: Faker, project: Project, users: list) -> int:
        n = random.randint(0, 3)  # noqa: S311
        for _ in range(n):
            Risk.objects.create(
                project=project,
                title=fake.sentence(nb_words=5).rstrip("."),
                description=fake.paragraph(nb_sentences=3),
                probability=random.choice(PROBABILITIES),  # noqa: S311
                impact=random.choice(IMPACTS),  # noqa: S311
                mitigation_plan=fake.paragraph(nb_sentences=2),
                risk_owner=random.choice(users),  # noqa: S311
                is_resolved=random.random() < 0.3,  # noqa: S311
            )
        return n

    # ── Issues ─────────────────────────────────────────────────────────────
    def _seed_issues(self, fake: Faker, project: Project, users: list) -> int:
        n = random.randint(0, 3)  # noqa: S311
        for _ in range(n):
            Issue.objects.create(
                project=project,
                title=fake.sentence(nb_words=5).rstrip("."),
                description=fake.paragraph(nb_sentences=3),
                severity=random.choice(SEVERITIES),  # noqa: S311
                assigned_to=random.choice(users),  # noqa: S311
                due_date=fake.future_date(end_date="+180d"),
                is_resolved=random.random() < 0.3,  # noqa: S311
            )
        return n

    # ── Procurements ───────────────────────────────────────────────────────
    def _seed_procurements(self, fake: Faker, project: Project, procurement_statuses: list) -> int:
        n = random.randint(0, 3)  # noqa: S311
        for _ in range(n):
            estimated = Decimal(random.randint(20_000, 5_000_000)).quantize(  # noqa: S311
                Decimal("1.00"),
            )
            has_actual = random.random() < 0.6  # noqa: S311
            actual: Decimal | None = None
            if has_actual:
                multiplier = Decimal(str(random.uniform(0.85, 1.15)))  # noqa: S311
                actual = (estimated * multiplier).quantize(Decimal("1.00"))
            award_date = None
            if actual is not None:
                award_date = fake.date_between(start_date="-1y", end_date="today")
            Procurement.objects.create(
                project=project,
                item_description=fake.sentence(nb_words=6).rstrip("."),
                procurement_method=random.choice(PROCUREMENT_METHODS),  # noqa: S311
                estimated_cost=estimated,
                actual_cost=actual,
                tender_date=fake.date_between(start_date="-1y", end_date="today"),
                award_date=award_date,
                status=random.choice(procurement_statuses),  # noqa: S311
            )
        return n

    # ── Project employees ──────────────────────────────────────────────────
    def _seed_employees(
        self,
        fake: Faker,
        project: Project,
        users: list,
        roles: list[Lookup],
    ) -> int:
        n = random.randint(0, min(3, len(users)))  # noqa: S311
        assigned = random.sample(users, n) if n else []
        for user in assigned:
            start = project.start_date or fake.date_between(start_date="-2y", end_date="-30d")
            ProjectEmployee.objects.create(
                project=project,
                user=user,
                role_on_project=random.choice(roles),  # noqa: S311
                start_date=start,
                end_date=None,
                daily_rate=Decimal(random.randint(500, 5_000)).quantize(Decimal("1.00")),  # noqa: S311
                is_current=True,
            )
        return len(assigned)

    # ── Monitoring visits ──────────────────────────────────────────────────
    def _seed_visits(self, fake: Faker, project: Project, users: list) -> int:
        n = random.randint(0, 2)  # noqa: S311
        for _ in range(n):
            visit_date = fake.date_between(start_date="-180d", end_date="today")
            physical = Decimal(random.randint(0, 100)).quantize(Decimal("0.01"))  # noqa: S311
            financial = Decimal(random.randint(0, int(physical) or 1)).quantize(Decimal("0.01"))  # noqa: S311
            visit = MonitoringVisit.objects.create(
                project=project,
                visit_date=visit_date,
                physical_progress_pct=physical,
                financial_progress_pct=financial,
                findings=fake.paragraph(nb_sentences=3),
                recommendations=fake.paragraph(nb_sentences=2),
                next_visit_date=visit_date + dt.timedelta(days=90),
                status_changed_to="",
            )
            team = random.sample(users, min(len(users), random.randint(1, 3)))  # noqa: S311
            visit.visit_team.set(team)
        return n

    # ── Evaluations ────────────────────────────────────────────────────────
    def _seed_evaluations(self, fake: Faker, project: Project, users: list) -> int:
        n = random.randint(0, 2)  # noqa: S311
        for _ in range(n):
            Evaluation.objects.create(
                project=project,
                evaluation_type=random.choice(EVAL_TYPES),  # noqa: S311
                evaluator=random.choice(users),  # noqa: S311
                evaluation_date=fake.date_between(start_date="-1y", end_date="today"),
                score=Decimal(random.randint(40, 100)).quantize(Decimal("0.01")),  # noqa: S311
                summary=fake.paragraph(nb_sentences=4),
            )
        return n
