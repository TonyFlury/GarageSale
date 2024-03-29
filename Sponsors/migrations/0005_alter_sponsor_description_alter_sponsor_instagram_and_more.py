# Generated by Django 4.0.6 on 2024-02-12 17:50

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Sponsors', '0004_alter_sponsor_facebook_alter_sponsor_website'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sponsor',
            name='description',
            field=models.TextField(max_length=1000),
        ),
        migrations.AlterField(
            model_name='sponsor',
            name='instagram',
            field=models.URLField(blank=True),
        ),
        migrations.AlterField(
            model_name='sponsor',
            name='twitter',
            field=models.URLField(blank=True),
        ),
    ]
