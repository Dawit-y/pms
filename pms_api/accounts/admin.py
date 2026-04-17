from django.contrib import admin

from .models import Permission
from .models import Role
from .models import User

admin.site.register(User)
admin.site.register(Permission)
admin.site.register(Role)
