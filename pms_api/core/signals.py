from django.dispatch import Signal

model_changed = Signal()  # args: instance, created
model_deleted = Signal()  # args: instance
