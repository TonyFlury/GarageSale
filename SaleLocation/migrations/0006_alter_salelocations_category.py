# Generated by Django 4.0.6 on 2024-03-01 08:18

import SaleLocation.models
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('SaleLocation', '0005_alter_salelocations_category'),
    ]

    operations = [
        migrations.AlterField(
            model_name='salelocations',
            name='category',
            field=SaleLocation.models.MultipleChoiceField(default=['Other'], max_length=500, null=True),
        ),
    ]
