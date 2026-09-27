from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fellows', '0009_fellow_accent_palette'),
    ]

    operations = [
        migrations.AlterField(
            model_name='fellow',
            name='accent_palette',
            field=models.CharField(
                choices=[
                    ('ocean', 'Ocean'),
                    ('sky', 'Sky'),
                    ('coral', 'Coral'),
                    ('violet', 'Violet'),
                    ('mint', 'Mint'),
                    ('forest', 'Forest'),
                    ('rose', 'Rose'),
                    ('amber', 'Amber'),
                ],
                default='ocean',
                max_length=12,
            ),
        ),
    ]
