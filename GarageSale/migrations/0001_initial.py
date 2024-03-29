# Generated by Django 4.0.6 on 2024-02-03 16:29

from django.db import migrations, models
import django_quill.fields


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='MOTD',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('use_from', models.DateField()),
                ('content', django_quill.fields.QuillField(default='')),
                ('synopsis', models.CharField(max_length=256, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='Settings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event_logo', models.ImageField(upload_to='')),
                ('event_date', models.DateField()),
                ('open_billboard_bookings', models.DateField()),
                ('close_billboard_bookings', models.DateField()),
                ('open_sales_bookings', models.DateField()),
                ('close_sales_bookings', models.DateField()),
            ],
        ),
    ]
