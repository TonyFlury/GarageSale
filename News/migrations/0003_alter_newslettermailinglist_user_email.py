# Generated by Django 4.0.6 on 2024-02-03 16:24

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('News', '0002_rename_entry_newslettermailinglist_user_email_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='newslettermailinglist',
            name='user_email',
            field=models.EmailField(max_length=254, unique=True),
        ),
    ]
