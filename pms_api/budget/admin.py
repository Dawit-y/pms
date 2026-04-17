from django.contrib import admin

from .models import BudgetForwardingStep
from .models import BudgetRequest

admin.site.register(BudgetRequest)
admin.site.register(BudgetForwardingStep)
