# Generated by Django 4.0.6 on 2024-02-18 23:34

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('GarageSale', '0007_alter_eventdata_close_billboard_bookings_and_more'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='eventdata',
            options={'permissions': [('CanCreate', 'Can create a new Event'), ('CanEdit', 'Can edit an existing Event'), ('CanDelete', 'Can delete an existing Event')]},
        ),
    ]
