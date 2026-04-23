# Generated migration to remove custom Permission and Role models

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_user_groups_user_user_permissions_and_more"),
    ]

    operations = [
        # Remove the role field from User
        migrations.RemoveField(
            model_name="user",
            name="role",
        ),
        # Delete the Role model
        migrations.DeleteModel(
            name="Role",
        ),
        # Delete the Permission model
        migrations.DeleteModel(
            name="Permission",
        ),
    ]
