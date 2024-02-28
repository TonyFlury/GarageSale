# Generated by Django 4.0.6 on 2024-02-21 16:46

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('News', '0004_alter_newsarticle_options_newsarticle_published'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='newsarticle',
            options={'default_permissions': (), 'permissions': [('CanCreateNews', 'Can create a news Article'), ('CanPublishNews', 'Can publish a news Article'), ('CanEditNews', 'Can edit a news Article'), ('CanDeleteNews', 'Can delete a news Article')]},
        ),
    ]
