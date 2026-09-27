from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fellows', '0008_alter_task_assigned_to'),
    ]

    operations = [
        migrations.AddField(
            model_name='fellow',
            name='accent_palette',
            field=models.CharField(
                choices=[('ocean', 'Ocean'), ('sky', 'Sky'), ('coral', 'Coral'), ('violet', 'Violet')],
                default='ocean',
                max_length=12,
            ),
        ),
    ]
