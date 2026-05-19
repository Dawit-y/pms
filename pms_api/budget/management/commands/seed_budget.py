"""
Seed BudgetRequest rows (and a short BudgetForwardingStep history) for
projects that don't have one yet. BudgetRequest has a OneToOne to Project,
so this command is naturally idempotent — it never duplicates per project.

Requires `seed_lookups` and `seed_projects` to have been run first.

Usage:
    uv run python manage.py seed_budget --count 30
    uv run python manage.py seed_budget --count 100 --flush
"""

from __future__ import annotations

import random
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.db import transaction
from faker import Faker

from pms_api.budget.models import BudgetForwardingStep
from pms_api.budget.models import BudgetRequest
from pms_api.lookups.models import Department
from pms_api.projects.models import Project

User = get_user_model()

STATUS_CHOICES = [s[0] for s in BudgetRequest.STATUS_CHOICES]
FISCAL_YEARS = ["2022/23", "2023/24", "2024/25", "2025/26", "2026/27"]


class Command(BaseCommand):
    help = (
        "Seed BudgetRequest rows for projects (one per project, OneToOne). "
        "Adds a short BudgetForwardingStep history for forwarded/approved states."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=25,
            help="Maximum number of budget requests to create (default: 25). "
            "Only projects without an existing BudgetRequest are eligible.",
        )
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Hard-delete existing budget requests and forwarding steps before seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        count: int = options["count"]
        flush: bool = options["flush"]

        if count <= 0:
            msg = "--count must be a positive integer"
            raise CommandError(msg)

        departments = list(Department.objects.exclude(parent=None))
        users = list(User.objects.all())

        if not departments:
            msg = "No departments found. Run `seed_lookups` first."
            raise CommandError(msg)
        if not users:
            msg = "No users found. Create at least one user first."
            raise CommandError(msg)

        if flush:
            self.stdout.write(self.style.WARNING("Flushing existing budget data..."))
            BudgetForwardingStep.all_objects.all().delete()
            BudgetRequest.all_objects.all().delete()

        eligible = list(Project.objects.filter(budget_request__isnull=True))
        if not eligible:
            self.stdout.write(self.style.WARNING("No projects without a budget request."))
            return

        target = min(count, len(eligible))
        chosen = random.sample(eligible, target)
        fake = Faker()

        created_requests = 0
        created_steps = 0
        for project in chosen:
            br, steps = self._create_request(fake, project, departments, users)
            if br is not None:
                created_requests += 1
                created_steps += steps

        self.stdout.write(
            self.style.SUCCESS(
                f"OK:Budget: {created_requests} requests, {created_steps} forwarding steps.",
            ),
        )

    def _create_request(
        self,
        fake: Faker,
        project: Project,
        departments: list[Department],
        users: list,
    ) -> tuple[BudgetRequest | None, int]:
        requested = project.total_budget or Decimal(
            random.randint(250_000, 50_000_000),  # noqa: S311
        ).quantize(Decimal("1.00"))

        status = random.choices(  # noqa: S311
            STATUS_CHOICES,
            weights=[1, 2, 2, 3, 4, 1, 1],
            k=1,
        )[0]

        approved_amount: Decimal | None = None
        if status == "approved":
            approved_amount = (requested * Decimal(str(random.uniform(0.75, 1.0)))).quantize(  # noqa: S311
                Decimal("1.00"),
            )

        actor = random.choice(users)  # noqa: S311
        current_dept = None
        if status not in {"draft", "approved", "rejected"}:
            current_dept = random.choice(departments)  # noqa: S311

        br = BudgetRequest.objects.create(
            project=project,
            requested_amount=requested,
            approved_amount=approved_amount,
            fiscal_year=random.choice(FISCAL_YEARS),  # noqa: S311
            justification=fake.paragraph(nb_sentences=4),
            status=status,
            current_department=current_dept,
            created_by=actor,
            updated_by=actor,
            owner=actor,
        )

        steps = 0
        if status in {"forwarded", "approved", "under_review"}:
            steps = self._seed_forwarding_history(br, departments, users, status)

        if status == "approved":
            project.is_active = True
            project.save(update_fields=["is_active"])

        return br, steps

    def _seed_forwarding_history(
        self,
        br: BudgetRequest,
        departments: list[Department],
        users: list,
        final_status: str,
    ) -> int:
        steps_n = random.randint(1, 3)  # noqa: S311
        chain = random.sample(departments, min(steps_n + 1, len(departments)))
        min_chain_len = 2
        if len(chain) < min_chain_len:
            return 0

        created = 0
        for i in range(len(chain) - 1):
            is_last = i == len(chain) - 2
            action = "approved" if is_last and final_status == "approved" else "forwarded"
            BudgetForwardingStep.objects.create(
                budget_request=br,
                from_department=chain[i],
                to_department=chain[i + 1],
                action=action,
                acted_by=random.choice(users),  # noqa: S311
                remarks="",
                step_number=i + 1,
            )
            created += 1
        return created
