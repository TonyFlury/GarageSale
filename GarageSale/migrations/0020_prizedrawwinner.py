import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("GarageSale", "0019_rename_transition_sub_category"),
        ("Contributors", "0005_contribution_classification_position"),
    ]

    operations = [
        migrations.CreateModel(
            name="PrizeDrawWinner",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("ticket_number", models.CharField(max_length=50)),
                ("phone", models.CharField(blank=True, max_length=32)),
                ("address", models.TextField(blank=True)),
                ("contribution", models.OneToOneField(
                    limit_choices_to={"cash": False, "classification": "prize_draw"},
                    on_delete=django.db.models.deletion.CASCADE, related_name="prize_draw_winner",
                    to="Contributors.contributions",
                )),
            ],
        ),
    ]
