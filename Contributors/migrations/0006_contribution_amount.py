from decimal import Decimal, InvalidOperation

from django.core.validators import MinValueValidator
from django.db import migrations, models


def migrate_cash_amounts(apps, schema_editor):
    contributions = apps.get_model('Contributors', 'Contributions').objects.using(schema_editor.connection.alias)
    for contribution in contributions.filter(cash=True, amount__isnull=True).iterator():
        try:
            value = Decimal((contribution.gift or '').strip().removeprefix('£').replace(',', '').strip())
            if not value.is_finite() or not 0 <= value <= Decimal('9999999999.99'):
                continue
            if value != value.quantize(Decimal('0.01')):
                continue
        except InvalidOperation:
            continue
        contributions.filter(pk=contribution.pk).update(amount=value, gift='')


def restore_cash_text(apps, schema_editor):
    contributions = apps.get_model('Contributors', 'Contributions').objects.using(schema_editor.connection.alias)
    for contribution in contributions.filter(cash=True, amount__isnull=False).iterator():
        if not contribution.gift:
            contributions.filter(pk=contribution.pk).update(gift=f'£{contribution.amount:.2f}')


class Migration(migrations.Migration):
    dependencies = [('Contributors', '0005_contribution_classification_position')]
    operations = [
        migrations.AddField(model_name='contributions', name='amount',
            field=models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
                                      validators=[MinValueValidator(Decimal('0'))])),
        migrations.RunPython(migrate_cash_amounts, restore_cash_text),
        migrations.AddConstraint(model_name='contributions', constraint=models.CheckConstraint(
            check=models.Q(amount__gte=0) | models.Q(amount__isnull=True), name='contribution_amount_nonnegative')),
    ]
