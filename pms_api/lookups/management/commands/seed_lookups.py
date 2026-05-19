"""
Seed lookup types, lookups, real Ethiopian locations, and a department tree.

Locations are NOT fake — they are real Ethiopian regions, zones, and woredas.
Other entities use the faker library for tri-lingual (en/am/or) text.

Usage:
    uv run python manage.py seed_lookups
    uv run python manage.py seed_lookups --count 30     # ~30 departments
    uv run python manage.py seed_lookups --flush        # wipe before seeding
"""

from __future__ import annotations

import random

from django.core.management.base import BaseCommand
from django.db import transaction
from faker import Faker

from pms_api.lookups.models import Department
from pms_api.lookups.models import Location
from pms_api.lookups.models import Lookup
from pms_api.lookups.models import LookupType

# ── Lookup catalog: every type the domain models actually filter on. ─────────
LOOKUP_CATALOG: dict[tuple[str, str], list[tuple[str, str]]] = {
    ("project_type", "Project Type"): [
        ("road", "Road Construction"),
        ("school", "School Construction"),
        ("hospital", "Hospital Construction"),
        ("dam", "Dam Construction"),
        ("bridge", "Bridge Construction"),
        ("water_supply", "Water Supply"),
        ("electrification", "Rural Electrification"),
        ("building", "Government Building"),
        ("irrigation", "Irrigation Scheme"),
    ],
    ("contractor_type", "Contractor Type"): [
        ("domestic", "Domestic Contractor"),
        ("foreign", "Foreign Contractor"),
        ("joint_venture", "Joint Venture"),
        ("sole_proprietor", "Sole Proprietor"),
    ],
    ("contract_status", "Contract Status"): [
        ("active", "Active"),
        ("completed", "Completed"),
        ("terminated", "Terminated"),
        ("suspended", "Suspended"),
    ],
    ("document_type", "Document Type"): [
        ("contract", "Contract"),
        ("drawing", "Engineering Drawing"),
        ("report", "Progress Report"),
        ("permit", "Permit"),
        ("certificate", "Certificate"),
        ("invoice", "Invoice"),
    ],
    ("procurement_status", "Procurement Status"): [
        ("planned", "Planned"),
        ("tendered", "Tendered"),
        ("awarded", "Awarded"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ],
    ("employee_role", "Employee Role"): [
        ("project_manager", "Project Manager"),
        ("engineer", "Engineer"),
        ("supervisor", "Supervisor"),
        ("technician", "Technician"),
        ("accountant", "Accountant"),
        ("foreman", "Foreman"),
    ],
}

# ── Real Ethiopian locations (region → zones → woredas). ─────────────────────
# Names in Amharic / Oromiffa are best-effort transliterations; expand as needed.
ETHIOPIAN_LOCATIONS: list[dict] = [
    {
        "code": "AA",
        "name_en": "Addis Ababa",
        "name_am": "አዲስ አበባ",
        "name_or": "Finfinnee",
        "type": "region",
        "children": [
            {"code": "AA-AK", "name_en": "Akaki Kality", "name_am": "አቃቂ ቃሊቲ", "type": "woreda"},
            {"code": "AA-BL", "name_en": "Bole", "name_am": "ቦሌ", "type": "woreda"},
            {"code": "AA-KZ", "name_en": "Kirkos", "name_am": "ቂርቆስ", "type": "woreda"},
            {"code": "AA-LB", "name_en": "Lideta", "name_am": "ልደታ", "type": "woreda"},
            {"code": "AA-YK", "name_en": "Yeka", "name_am": "የካ", "type": "woreda"},
        ],
    },
    {
        "code": "DD",
        "name_en": "Dire Dawa",
        "name_am": "ድሬዳዋ",
        "name_or": "Dirre Dhawaa",
        "type": "region",
        "children": [
            {"code": "DD-GU", "name_en": "Gurgura", "name_am": "ጉርጉራ", "type": "woreda"},
            {"code": "DD-JL", "name_en": "Jeldessa", "name_am": "ጀልዴሳ", "type": "woreda"},
        ],
    },
    {
        "code": "OR",
        "name_en": "Oromia",
        "name_am": "ኦሮሚያ",
        "name_or": "Oromiyaa",
        "type": "region",
        "children": [
            {
                "code": "OR-WS",
                "name_en": "West Shewa",
                "name_am": "ምዕራብ ሸዋ",
                "name_or": "Shawaa Lixaa",
                "type": "zone",
                "children": [
                    {"code": "OR-WS-AB", "name_en": "Ambo", "name_am": "አምቦ", "type": "woreda"},
                    {"code": "OR-WS-BK", "name_en": "Bako Tibe", "type": "woreda"},
                    {"code": "OR-WS-GD", "name_en": "Gindeberet", "type": "woreda"},
                ],
            },
            {
                "code": "OR-ES",
                "name_en": "East Shewa",
                "name_am": "ምስራቅ ሸዋ",
                "name_or": "Shawaa Bahaa",
                "type": "zone",
                "children": [
                    {
                        "code": "OR-ES-AD",
                        "name_en": "Adama",
                        "name_am": "አዳማ",
                        "type": "woreda",
                    },
                    {
                        "code": "OR-ES-BS",
                        "name_en": "Bishoftu",
                        "name_am": "ቢሾፍቱ",
                        "type": "woreda",
                    },
                    {
                        "code": "OR-ES-MJ",
                        "name_en": "Mojo",
                        "name_am": "ሞጆ",
                        "type": "woreda",
                    },
                ],
            },
            {
                "code": "OR-AR",
                "name_en": "Arsi",
                "name_am": "አርሲ",
                "name_or": "Arsii",
                "type": "zone",
                "children": [
                    {"code": "OR-AR-AS", "name_en": "Asella", "name_am": "አሰላ", "type": "woreda"},
                    {"code": "OR-AR-RB", "name_en": "Robe", "type": "woreda"},
                ],
            },
            {
                "code": "OR-JM",
                "name_en": "Jimma",
                "name_am": "ጅማ",
                "name_or": "Jimma",
                "type": "zone",
                "children": [
                    {"code": "OR-JM-JM", "name_en": "Jimma Town", "type": "woreda"},
                    {"code": "OR-JM-AG", "name_en": "Agaro", "type": "woreda"},
                ],
            },
        ],
    },
    {
        "code": "AM",
        "name_en": "Amhara",
        "name_am": "አማራ",
        "name_or": "Amaaraa",
        "type": "region",
        "children": [
            {
                "code": "AM-NS",
                "name_en": "North Shewa",
                "name_am": "ሰሜን ሸዋ",
                "type": "zone",
                "children": [
                    {
                        "code": "AM-NS-DB",
                        "name_en": "Debre Berhan",
                        "name_am": "ደብረ ብርሃን",
                        "type": "woreda",
                    },
                    {"code": "AM-NS-SH", "name_en": "Shewa Robit", "type": "woreda"},
                ],
            },
            {
                "code": "AM-SW",
                "name_en": "South Wollo",
                "name_am": "ደቡብ ወሎ",
                "type": "zone",
                "children": [
                    {
                        "code": "AM-SW-DS",
                        "name_en": "Dessie",
                        "name_am": "ደሴ",
                        "type": "woreda",
                    },
                    {
                        "code": "AM-SW-KB",
                        "name_en": "Kombolcha",
                        "name_am": "ኮምቦልቻ",
                        "type": "woreda",
                    },
                ],
            },
            {
                "code": "AM-WG",
                "name_en": "West Gojjam",
                "name_am": "ምዕራብ ጎጃም",
                "type": "zone",
                "children": [
                    {
                        "code": "AM-WG-BD",
                        "name_en": "Bahir Dar",
                        "name_am": "ባህር ዳር",
                        "type": "woreda",
                    },
                    {"code": "AM-WG-FL", "name_en": "Finote Selam", "type": "woreda"},
                ],
            },
            {
                "code": "AM-NG",
                "name_en": "North Gondar",
                "name_am": "ሰሜን ጎንደር",
                "type": "zone",
                "children": [
                    {"code": "AM-NG-GD", "name_en": "Gondar", "name_am": "ጎንደር", "type": "woreda"},
                    {"code": "AM-NG-DB", "name_en": "Debark", "type": "woreda"},
                ],
            },
        ],
    },
    {
        "code": "TG",
        "name_en": "Tigray",
        "name_am": "ትግራይ",
        "name_or": "Tigraay",
        "type": "region",
        "children": [
            {
                "code": "TG-CT",
                "name_en": "Central Tigray",
                "type": "zone",
                "children": [
                    {"code": "TG-CT-AX", "name_en": "Axum", "name_am": "አክሱም", "type": "woreda"},
                    {"code": "TG-CT-AD", "name_en": "Adwa", "type": "woreda"},
                ],
            },
            {
                "code": "TG-ET",
                "name_en": "Eastern Tigray",
                "type": "zone",
                "children": [
                    {"code": "TG-ET-WK", "name_en": "Wukro", "type": "woreda"},
                    {"code": "TG-ET-AT", "name_en": "Atsbi", "type": "woreda"},
                ],
            },
            {
                "code": "TG-MK",
                "name_en": "Mekelle",
                "name_am": "መቀሌ",
                "type": "zone",
                "children": [
                    {"code": "TG-MK-AY", "name_en": "Ayder", "type": "woreda"},
                    {"code": "TG-MK-QH", "name_en": "Quiha", "type": "woreda"},
                ],
            },
        ],
    },
    {
        "code": "SN",
        "name_en": "SNNPR",
        "name_am": "ደቡብ",
        "type": "region",
        "children": [
            {
                "code": "SN-GR",
                "name_en": "Gurage",
                "type": "zone",
                "children": [
                    {"code": "SN-GR-WK", "name_en": "Wolkite", "type": "woreda"},
                    {"code": "SN-GR-BN", "name_en": "Butajira", "type": "woreda"},
                ],
            },
            {
                "code": "SN-HD",
                "name_en": "Hadiya",
                "type": "zone",
                "children": [
                    {"code": "SN-HD-HS", "name_en": "Hosaena", "name_am": "ሆሳዕና", "type": "woreda"},
                ],
            },
            {
                "code": "SN-WL",
                "name_en": "Wolayita",
                "type": "zone",
                "children": [
                    {"code": "SN-WL-SD", "name_en": "Sodo", "name_am": "ሶዶ", "type": "woreda"},
                ],
            },
        ],
    },
    {
        "code": "SD",
        "name_en": "Sidama",
        "name_am": "ሲዳማ",
        "type": "region",
        "children": [
            {"code": "SD-HW", "name_en": "Hawassa", "name_am": "ሐዋሳ", "type": "woreda"},
            {"code": "SD-YR", "name_en": "Yirgalem", "type": "woreda"},
        ],
    },
    {
        "code": "AF",
        "name_en": "Afar",
        "name_am": "አፋር",
        "type": "region",
        "children": [
            {"code": "AF-SM", "name_en": "Semera", "name_am": "ሰመራ", "type": "woreda"},
            {"code": "AF-AS", "name_en": "Asaita", "type": "woreda"},
        ],
    },
    {
        "code": "SO",
        "name_en": "Somali",
        "name_am": "ሶማሌ",
        "type": "region",
        "children": [
            {"code": "SO-JJ", "name_en": "Jijiga", "name_am": "ጅጅጋ", "type": "woreda"},
            {"code": "SO-DG", "name_en": "Degehabur", "type": "woreda"},
        ],
    },
    {
        "code": "BG",
        "name_en": "Benishangul-Gumuz",
        "name_am": "ቤንሻንጉል ጉሙዝ",
        "type": "region",
        "children": [
            {"code": "BG-AS", "name_en": "Assosa", "name_am": "አሶሳ", "type": "woreda"},
        ],
    },
    {
        "code": "GM",
        "name_en": "Gambela",
        "name_am": "ጋምቤላ",
        "type": "region",
        "children": [
            {"code": "GM-GM", "name_en": "Gambela Town", "type": "woreda"},
        ],
    },
    {
        "code": "HR",
        "name_en": "Harari",
        "name_am": "ሐረሪ",
        "type": "region",
        "children": [
            {"code": "HR-HR", "name_en": "Harar", "name_am": "ሐረር", "type": "woreda"},
        ],
    },
]

DEPARTMENT_ROOT = ("BUR", "Bureau of Project Management")
DEPARTMENT_DIRECTORATES = [
    ("PLN", "Planning & Programming Directorate"),
    ("MON", "Monitoring & Evaluation Directorate"),
    ("FIN", "Finance Directorate"),
    ("PRC", "Procurement Directorate"),
    ("HR", "Human Resources Directorate"),
    ("IT", "ICT Directorate"),
    ("LEG", "Legal Affairs Directorate"),
    ("AUD", "Internal Audit Directorate"),
]


class Command(BaseCommand):
    help = (
        "Seed lookup types, lookups, real Ethiopian location tree, and a department tree. "
        "Locations are real; other entities use Faker for tri-lingual text."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=20,
            help="Number of sub-departments to create under each directorate (default: 20 total).",
        )
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Hard-delete existing lookups, locations, and departments before seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        count: int = options["count"]
        flush: bool = options["flush"]

        if flush:
            self.stdout.write(self.style.WARNING("Flushing lookups, locations, departments..."))
            Lookup.all_objects.all().delete()
            LookupType.all_objects.all().delete()
            Location.all_objects.all().delete()
            Department.all_objects.all().delete()

        self._seed_lookups()
        self._seed_locations()
        self._seed_departments(count)

        self.stdout.write(self.style.SUCCESS("OK:Lookups seeding complete."))

    def _seed_lookups(self):
        created_types = 0
        created_values = 0
        for (type_code, type_name_en), values in LOOKUP_CATALOG.items():
            lookup_type, type_created = LookupType.objects.get_or_create(
                code=type_code,
                defaults={
                    "name_en": type_name_en,
                    "name_am": "",
                    "name_or": "",
                    "is_active": True,
                },
            )
            if type_created:
                created_types += 1
            for sort_order, (value_code, value_name_en) in enumerate(values, start=1):
                _, val_created = Lookup.objects.get_or_create(
                    lookup_type=lookup_type,
                    code=value_code,
                    defaults={
                        "name_en": value_name_en,
                        "name_am": "",
                        "name_or": "",
                        "sort_order": sort_order,
                        "is_active": True,
                    },
                )
                if val_created:
                    created_values += 1
        self.stdout.write(
            f"  Lookups: {created_types} new types, {created_values} new values.",
        )

    def _seed_locations(self):
        created = 0
        for region in ETHIOPIAN_LOCATIONS:
            region_obj, was_created = Location.objects.get_or_create(
                code=region["code"],
                defaults={
                    "name_en": region["name_en"],
                    "name_am": region.get("name_am", ""),
                    "name_or": region.get("name_or", ""),
                    "location_type": region["type"],
                    "parent": None,
                },
            )
            if was_created:
                created += 1
            created += self._seed_location_children(region_obj, region.get("children", []))
        self.stdout.write(f"  Locations: {created} new nodes.")

    def _seed_location_children(self, parent: Location, children: list[dict]) -> int:
        created = 0
        for child in children:
            child_obj, was_created = Location.objects.get_or_create(
                code=child["code"],
                defaults={
                    "name_en": child["name_en"],
                    "name_am": child.get("name_am", ""),
                    "name_or": child.get("name_or", ""),
                    "location_type": child["type"],
                    "parent": parent,
                },
            )
            if was_created:
                created += 1
            created += self._seed_location_children(child_obj, child.get("children", []))
        return created

    def _seed_departments(self, count: int):
        fake = Faker()
        root, _ = Department.objects.get_or_create(
            code=DEPARTMENT_ROOT[0],
            defaults={"name_en": DEPARTMENT_ROOT[1], "parent": None},
        )

        directorates: list[Department] = []
        for code, name in DEPARTMENT_DIRECTORATES:
            dept, _ = Department.objects.get_or_create(
                code=code,
                defaults={"name_en": name, "parent": root},
            )
            directorates.append(dept)

        sub_target = max(count, 0)
        existing_subs = Department.objects.exclude(
            code__in=[DEPARTMENT_ROOT[0], *[d[0] for d in DEPARTMENT_DIRECTORATES]],
        ).count()
        to_create = max(sub_target - existing_subs, 0)

        created_subs = 0
        for i in range(to_create):
            parent = random.choice(directorates)  # noqa: S311
            code = f"SUB-{parent.code}-{existing_subs + i + 1:03d}"
            Department.objects.create(
                code=code,
                name_en=f"{fake.last_name()} Team — {parent.name_en.split(' Directorate')[0]}",
                parent=parent,
            )
            created_subs += 1

        self.stdout.write(
            f"  Departments: root + {len(DEPARTMENT_DIRECTORATES)} directorates + "
            f"{created_subs} new sub-teams.",
        )
