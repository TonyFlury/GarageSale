from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('user_management', '0004_alter_teammember_role'),
        ('user_management', '0005_volunteer_profile'),
    ]
    operations = [
        migrations.AlterField(
            model_name='teammember', name='role',
            field=models.CharField(choices=[(role, role) for role in (
                'Committee Member', 'Treasurer', 'Chairperson', 'Secretary', 'Volunteer',
            )]),
        ),
    ]
