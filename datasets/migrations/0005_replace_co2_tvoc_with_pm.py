from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('datasets', '0004_dataset_box_temp_dataset_co2_ppm_dataset_is_raining_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='dataset',
            name='co2_ppm',
        ),
        migrations.RemoveField(
            model_name='dataset',
            name='tvoc_ppb',
        ),
        migrations.AddField(
            model_name='dataset',
            name='pm1_0',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='dataset',
            name='pm2_5',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='dataset',
            name='pm10',
            field=models.IntegerField(default=0),
        ),
    ]
