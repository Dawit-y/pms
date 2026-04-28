from django.contrib import admin

from .models import Department
from .models import Location
from .models import Lookup
from .models import LookupType

admin.site.register(LookupType)
admin.site.register(Lookup)
admin.site.register(Department)
admin.site.register(Location)
