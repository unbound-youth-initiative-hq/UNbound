from django.db import migrations


UN_SDGS = [
        {"code": 1, "name": "No Poverty", "color": "#E5243B"},
        {"code": 2, "name": "Zero Hunger", "color": "#DDA63A"},
        {"code": 3, "name": "Good Health & Well-Being", "color": "#4C9F38"},
        {"code": 4, "name": "Quality Education", "color": "#C5192D"},
        {"code": 5, "name": "Gender Equality", "color": "#FF3A21"},
        {"code": 6, "name": "Clean Water & Sanitation", "color": "#26BDE2"},
        {"code": 7, "name": "Affordable & Clean Energy", "color": "#FCC30B"},
        {"code": 8, "name": "Decent Work & Economic Growth", "color": "#A21942"},
        {"code": 9, "name": "Industry, Innovation & Infrastructure", "color": "#FD6925"},
        {"code": 10, "name": "Reduced Inequalities", "color": "#DD1367"},
        {"code": 11, "name": "Sustainable Cities & Communities", "color": "#FD9D24"},
        {"code": 12, "name": "Responsible Consumption & Production", "color": "#BF8B2E"},
        {"code": 13, "name": "Climate Action", "color": "#3F7E44"},
        {"code": 14, "name": "Life Below Water", "color": "#0A97D9"},
        {"code": 15, "name": "Life on Land", "color": "#56C02B"},
        {"code": 16, "name": "Peace, Justice & Strong Institutions", "color": "#00689D"},
        {"code": 17, "name": "Partnerships for the Goals", "color": "#19486A"},
    ]


def seed_missing_goals(apps, schema_editor):
    goals = apps.get_model('fellows', 'SDG').objects.using(schema_editor.connection.alias)
    goals.bulk_create([goals.model(**goal) for goal in UN_SDGS], ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [('fellows', '0018_external_resources')]
    operations = [migrations.RunPython(seed_missing_goals, migrations.RunPython.noop)]
