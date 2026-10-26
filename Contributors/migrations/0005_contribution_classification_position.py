from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("Contributors", "0004_contributor_optional_fields")]

    operations = [
        migrations.AddField(
            model_name="contributions", name="classification",
            field=models.CharField(max_length=12, choices=[("unclassified", "Unclassified"),
                ("prize_draw", "Prize Draw"), ("tombola", "Tombola")], default="unclassified"),
        ),
        migrations.AddField(model_name="contributions", name="position", field=models.PositiveIntegerField(default=0)),
    ]
