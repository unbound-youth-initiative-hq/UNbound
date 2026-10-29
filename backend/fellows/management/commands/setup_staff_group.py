from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission

class Command(BaseCommand):
    help = 'Create/update the UNbound coordinators permission group. Does not grant anyone access.'
    def handle(self, *args, **options):
        group, _ = Group.objects.get_or_create(name='UNbound coordinators')
        models = ['chapter', 'cohort', 'phase', 'fellow', 'task', 'availabilityrequest', 'badge', 'fellowbadge', 'invitecode', 'sdg']
        permissions = list(Permission.objects.filter(content_type__app_label='fellows', content_type__model__in=models))
        permissions += list(Permission.objects.filter(content_type__app_label='auth', codename='view_user'))
        permissions += list(Permission.objects.filter(content_type__app_label='fellows', codename='view_reminderdelivery'))
        group.permissions.set(permissions)
        self.stdout.write(self.style.SUCCESS('UNbound coordinators group updated. Assign it and Staff status to approved operators in Users.'))
