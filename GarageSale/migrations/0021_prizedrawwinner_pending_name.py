from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("GarageSale", "0020_prizedrawwinner")]
    operations = [
        migrations.AlterField(model_name="prizedrawwinner", name="name", field=models.CharField(blank=True, max_length=200)),
    ]
