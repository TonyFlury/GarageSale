# Generated manually to restore the nomination feature.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('GarageSale', '0018_motd_htnl_content'),
    ]

    operations = [
        migrations.CreateModel(
            name='Nomination',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nominee', models.CharField(max_length=100, verbose_name='Organisation name')),
                ('contact_email', models.EmailField(blank=True, max_length=254, null=True, verbose_name='a contact email address')),
                ('contact_phone', models.CharField(blank=True, max_length=20, verbose_name='a contact phone number')),
                ('nominator', models.CharField(blank=True, max_length=100, verbose_name='your name')),
                ('nominator_email', models.EmailField(blank=True, max_length=254, null=True, verbose_name='your email address')),
                ('anonymous', models.BooleanField(default=False, help_text='Do you want to hide your name [from the organisation that you are nominating')),
                ('community_activities', models.TextField(default='', verbose_name='how does the organisation benefit Brantham ?')),
                ('spending_plans', models.TextField(default='', verbose_name='how might the organisation might spend any funds')),
                ('nomination_date', models.DateTimeField(auto_now_add=True)),
                ('status', models.CharField(choices=[('New', 'New'), ('Accepted', 'Accepted'), ('Rejected', 'Rejected'), ('Completed', 'Completed')], default='New', max_length=100)),
                ('reason', models.TextField(blank=True, default='', null=True, verbose_name='rejection reason')),
            ],
        ),
    ]
