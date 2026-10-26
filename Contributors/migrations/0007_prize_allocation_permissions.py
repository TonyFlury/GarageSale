from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('Contributors', '0006_contribution_amount')]

    operations = [
        migrations.AlterModelOptions(
            name='contributions',
            options={'permissions': [
                ('view_prize_allocation', 'Can view prize allocation'),
                ('change_prize_allocation', 'Can categorise and order prizes'),
            ]},
        ),
    ]
