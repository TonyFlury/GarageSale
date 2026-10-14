from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("Contributors", "0003_repair_history_details")]

    operations = [
        migrations.AlterField(
            model_name="contributor", name="phone",
            field=models.CharField(blank=True, max_length=12),
        ),
        migrations.AlterField(
            model_name="contributor", name="description",
            field=models.TextField(blank=True, max_length=1000),
        ),
    ]
