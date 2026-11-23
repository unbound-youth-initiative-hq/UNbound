from datetime import datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo, available_timezones

from django.conf import settings
from django.utils import timezone


@lru_cache(maxsize=1)
def meeting_timezone_choices():
    """Group geographical IANA zone names by region, including islands and subregions."""
    regions = {}
    for zone in sorted(available_timezones()):
        region, _, city = zone.partition('/')
        if region in {'Africa', 'America', 'Antarctica', 'Arctic', 'Asia', 'Atlantic',
                      'Australia', 'Europe', 'Indian', 'Pacific'}:
            regions.setdefault(region, []).append((zone, city.replace('_', ' ').replace('/', ' / ')))
    return [('Universal', [('UTC', 'UTC')]), *regions.items()]


def localized_poll_days(poll, zone_name):
    """Display each Monterrey slot in the fellow's zone while preserving its storage key."""
    local_zone = ZoneInfo(zone_name)
    source_zone = ZoneInfo(settings.TIME_ZONE)
    today = timezone.localdate(timezone=local_zone)
    days = []
    day_count = (poll.end_date - poll.start_date).days + 1
    if not (0 <= poll.start_hour < poll.end_hour <= 24 and 1 <= day_count <= 42):
        return days
    for date in poll.candidate_dates():
        start = datetime.combine(date, time(poll.start_hour), tzinfo=source_zone)
        slots = [(start + timedelta(hours=i)).astimezone(local_zone)
                 for i in range(poll.end_hour - poll.start_hour)]
        first = slots[0].date()
        labels = []
        for slot in slots:
            label = slot.strftime('%I:%M %p').lstrip('0')
            if slot.fold or slot.replace(fold=1).utcoffset() != slot.utcoffset():
                label += ' ' + slot.strftime('%z')
            if slot.date() != first:
                label += ' (+1 day)'
            labels.append(label)
        days.append({
            'date': date.isoformat(), 'dayOfWeek': (date.weekday() + 1) % 7,
            'dayName': first.strftime('%a'), 'monthName': first.strftime('%b'),
            'dayNum': first.day, 'isToday': first == today, 'hours': labels,
        })
    return days
