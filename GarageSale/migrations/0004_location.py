# Generated by Django 4.0.6 on 2024-02-06 10:23

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('GarageSale', '0003_alter_eventdata_managers'),
    ]

    operations = [
        migrations.CreateModel(
            name='Location',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('house_number', models.CharField(max_length=80)),
                ('street_name', models.CharField(max_length=200)),
                ('town', models.CharField(default='Brantham', max_length=100)),
                ('postcode', models.CharField(max_length=10)),
                ('phone', models.CharField(max_length=12)),
                ('mobile', models.CharField(max_length=12)),
                ('user', models.ForeignKey(blank=True, on_delete=django.db.models.deletion.CASCADE, related_name='locations', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
