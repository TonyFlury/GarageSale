# Generated by Django 4.0.6 on 2024-02-12 17:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Sponsors', '0003_sponsor_event'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sponsor',
            name='facebook',
            field=models.URLField(blank=True),
        ),
        migrations.AlterField(
            model_name='sponsor',
            name='website',
            field=models.URLField(blank=True),
        ),
    ]
