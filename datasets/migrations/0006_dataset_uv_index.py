from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('datasets', '0005_replace_co2_tvoc_with_pm'),
    ]

    operations = [
        migrations.AddField(
            model_name='dataset',
            name='uv_index',
            field=models.IntegerField(default=0),
        ),
    ]
