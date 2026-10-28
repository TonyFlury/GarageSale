"""Distinguish invite acceptance from payment-backed confirmation."""
from django.db import migrations


def forwards(apps, schema_editor):
    Status = apps.get_model('Contributors', 'ContributorEvent')
    Payment = apps.get_model('CraftMarket', 'PitchPayment')
    alias = schema_editor.connection.alias
    paid_records = Payment.objects.using(alias).values('status_record_id')
    market = Status.objects.using(alias).filter(contributor__contributor_type='Marketer')
    # An old acceptance never proves payment. Preserve any payment-backed Confirmed rows.
    market.filter(status='Confirmed').exclude(pk__in=paid_records).update(status='Fee Pending')
    market.filter(status='Pending').update(status='Fee Pending')
    market.filter(status='Fee paid').update(status='Confirmed')


def backwards(apps, schema_editor):
    Status = apps.get_model('Contributors', 'ContributorEvent')
    market = Status.objects.using(schema_editor.connection.alias).filter(contributor__contributor_type='Marketer')
    market.filter(status='Confirmed').update(status='Fee paid')
    market.filter(status='Fee Pending').update(status='Confirmed')


class Migration(migrations.Migration):
    dependencies = [
        ('CraftMarket', '0013_pitch_payment'),
        ('Contributors', '0010_alter_contributorevent_status'),
    ]
    operations = [migrations.RunPython(forwards, backwards)]
