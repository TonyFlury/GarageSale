from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("GarageSale", "0018_motd_htnl_content")]

    operations = [
        migrations.RemoveIndex(model_name="communicationtemplate", name="CategoryTransitionByDate"),
        migrations.RenameField(model_name="communicationtemplate", old_name="transition", new_name="sub_category"),
        migrations.AddIndex(
            model_name="communicationtemplate",
            index=models.Index(fields=["category", "sub_category", "-use_from"], name="CategorySubCategoryByDate"),
        ),
    ]
