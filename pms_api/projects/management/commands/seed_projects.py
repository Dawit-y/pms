"""
Seed Project rows and ProjectStatus history.

Requires lookup data + a location tree + at least one department (run
`seed_lookups` first) and at least one User (create a superuser, or
`seed_users` if present). The seeder does not create users.

Usage:
    uv run python manage.py seed_projects --count 50
    uv run python manage.py seed_projects --count 200 --flush
"""

from __future__ import annotations

import datetime as dt
import random
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.db import transaction
from faker import Faker

from pms_api.lookups.models import Department
from pms_api.lookups.models import Location
from pms_api.lookups.models import Lookup
from pms_api.projects.models import Project
from pms_api.projects.models import ProjectStatus

User = get_user_model()

MIN_BUDGET = Decimal("250000")
MAX_BUDGET = Decimal("75000000")
STATUS_FLOW = [
    "registered",
    "budget_requested",
    "budget_approved",
    "in_progress",
]


class Command(BaseCommand):
    help = "Seed fake Project rows and a short ProjectStatus history per project."

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=25,
            help="Number of projects to create (default: 25).",
        )
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Hard-delete existing projects (and cascaded status history) before seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        count: int = options["count"]
        flush: bool = options["flush"]

        if count <= 0:
            msg = "--count must be a positive integer"
            raise CommandError(msg)

        project_types = list(Lookup.objects.filter(lookup_type__code="project_type"))
        locations = list(Location.objects.filter(location_type="woreda"))
        if not locations:
            locations = list(Location.objects.all())
        departments = list(Department.objects.exclude(parent=None))
        users = list(User.objects.all())

        if not project_types:
            msg = "No project_type lookups found. Run `seed_lookups` first."
            raise CommandError(msg)
        if not locations:
            msg = "No locations found. Run `seed_lookups` first."
            raise CommandError(msg)
        if not departments:
            msg = "No departments found. Run `seed_lookups` first."
            raise CommandError(msg)
        if not users:
            msg = "No users found. Create at least one user (e.g. createsuperuser) first."
            raise CommandError(msg)

        if flush:
            self.stdout.write(self.style.WARNING("Flushing existing projects..."))
            Project.all_objects.all().delete()

        fake = Faker()
        existing = Project.all_objects.count()
        created_projects = 0
        created_statuses = 0

        for i in range(count):
            seq = existing + i + 1
            code = f"PRJ-{seq:06d}"
            if Project.all_objects.filter(code=code).exists():
                continue

            project_type = random.choice(project_types)  # noqa: S311
            start_date = fake.date_between(start_date="-3y", end_date="-30d")
            planned_end = start_date + dt.timedelta(days=random.randint(180, 1825))  # noqa: S311
            budget = Decimal(
                random.randint(int(MIN_BUDGET), int(MAX_BUDGET)),  # noqa: S311
            ).quantize(Decimal("1.00"))
            creator = random.choice(users)  # noqa: S311

            project = Project.objects.create(
                code=code,
                title=f"{project_type.name_en}: {fake.street_name()} {fake.city()}",
                description=fake.paragraph(nb_sentences=4),
                project_type=project_type,
                location=random.choice(locations),  # noqa: S311
                implementing_department=random.choice(departments),  # noqa: S311
                start_date=start_date,
                planned_end_date=planned_end,
                actual_end_date=None,
                total_budget=budget,
                is_active=False,
                created_by=creator,
                updated_by=creator,
                owner=creator,
            )
            created_projects += 1
            created_statuses += self._seed_status_history(project, users)

        self.stdout.write(
            self.style.SUCCESS(
                f"OK:Projects: {created_projects} created, {created_statuses} status rows.",
            ),
        )

    def _seed_status_history(self, project: Project, users: list) -> int:
        steps = random.randint(1, len(STATUS_FLOW))  # noqa: S311
        latest = None
        physical = Decimal("0.00")
        financial = Decimal("0.00")
        for status_code in STATUS_FLOW[:steps]:
            if status_code == "in_progress":
                physical = Decimal(random.randint(5, 95)).quantize(Decimal("0.01"))  # noqa: S311
                financial = Decimal(random.randint(5, int(physical))).quantize(  # noqa: S311
                    Decimal("0.01"),
                )
            latest = ProjectStatus.objects.create(
                project=project,
                status=status_code,
                changed_by=random.choice(users),  # noqa: S311
                visit_date=project.start_date,
                remarks="",
                physical_progress_pct=physical,
                financial_progress_pct=financial,
            )
        if latest is not None:
            project.current_status = latest
            if latest.status in {"budget_approved", "in_progress"}:
                project.is_active = True
            project.save(update_fields=["current_status", "is_active"])
        return steps
