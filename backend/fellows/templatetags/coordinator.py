from django import template

from ..admin import overdue_tasks
from ..models import AvailabilityRequest, Task

register = template.Library()


@register.simple_tag
def coordinator_counts(user):
    counts = {}
    if user.has_perm('fellows.view_task') or user.has_perm('fellows.change_task'):
        counts['overdue'] = overdue_tasks(Task.objects.all()).count()
    if user.has_perm('fellows.view_availabilityrequest') or user.has_perm('fellows.change_availabilityrequest'):
        counts['open_polls'] = AvailabilityRequest.objects.filter(is_active=True).count()
    return counts
