"""
Factory Boy factories for accounts app models.
"""

import factory
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from factory.django import DjangoModelFactory

User = get_user_model()


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    phone = factory.Sequence(lambda n: f"+25191{n:07d}")  # Max 20 chars
    is_active = True
    is_staff = False

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """Override to use create_user method."""
        password = kwargs.pop("password", "testpass123")
        user = model_class.objects.create_user(*args, **kwargs)
        user.set_password(password)
        user.save()
        return user


class StaffUserFactory(UserFactory):
    is_staff = True


class SuperUserFactory(UserFactory):
    is_staff = True
    is_superuser = True

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        password = kwargs.pop("password", "testpass123")
        return model_class.objects.create_superuser(*args, password=password, **kwargs)


class GroupFactory(DjangoModelFactory):
    class Meta:
        model = Group

    name = factory.Sequence(lambda n: f"Group {n}")
