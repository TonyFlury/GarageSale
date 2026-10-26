from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('GarageSale', '0024_merge_nominations_contributors')]
    # General is unmanaged: retire its state without creating/dropping a table.
    operations = [migrations.DeleteModel(name='General')]
