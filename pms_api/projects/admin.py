from django.contrib import admin

from .models import Project
from .models import ProjectStatus

admin.site.register(Project)
admin.site.register(ProjectStatus)
