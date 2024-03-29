# Generated by Django 4.0.6 on 2024-02-01 11:03

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Sponsor',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('company_name', models.CharField(max_length=120)),
                ('logo', models.FileField(upload_to='')),
                ('description', models.TextField(max_length=256)),
                ('website', models.URLField()),
                ('facebook', models.URLField()),
                ('twitter', models.CharField(max_length=80)),
                ('instagram', models.CharField(max_length=80)),
                ('email', models.EmailField(max_length=254)),
                ('phone', models.CharField(max_length=12)),
                ('creation_date', models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]
