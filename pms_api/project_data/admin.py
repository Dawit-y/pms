from django.contrib import admin

from .models import Contractor
from .models import ContractorAssignment
from .models import Evaluation
from .models import Issue
from .models import Milestone
from .models import MonitoringVisit
from .models import Payment
from .models import Procurement
from .models import ProjectDocument
from .models import ProjectEmployee
from .models import Risk

admin.site.register(Contractor)
admin.site.register(ContractorAssignment)
admin.site.register(Payment)
admin.site.register(Procurement)
admin.site.register(Evaluation)
admin.site.register(Issue)
admin.site.register(MonitoringVisit)
admin.site.register(ProjectDocument)
admin.site.register(ProjectEmployee)
admin.site.register(Risk)
admin.site.register(Milestone)
