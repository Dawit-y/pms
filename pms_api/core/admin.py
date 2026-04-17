from django.contrib import admin

from .models.access_log import AccessLog
from .models.notifications import Notification

admin.site.register(AccessLog)
admin.site.register(Notification)
