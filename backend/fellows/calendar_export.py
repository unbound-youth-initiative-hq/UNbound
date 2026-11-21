from datetime import UTC
from urllib.parse import urlsplit

from django.conf import settings


def _text(value):
    return (
        value.replace('\\', '\\\\').replace('\r\n', '\n').replace('\r', '\n')
        .replace('\n', '\\n').replace(';', '\\;').replace(',', '\\,')
    )


def _fold(line):
    parts = []
    segment = []
    octets = 0
    for character in line:
        width = len(character.encode('utf-8'))
        if octets + width > 75:
            parts.append(''.join(segment))
            segment = [' ']
            octets = 1
        segment.append(character)
        octets += width
    parts.append(''.join(segment))
    return '\r\n'.join(parts)


def meeting_calendar(meeting):
    host = urlsplit(settings.SITE_BASE_URL).hostname or 'unbound.org'
    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//UNbound//Confirmed meetings//EN',
        'BEGIN:VEVENT',
        f'UID:meeting-{meeting.pk}@{host}',
        f'DTSTAMP:{meeting.updated_at.astimezone(UTC):%Y%m%dT%H%M%SZ}',
        f'DTSTART:{meeting.starts_at.astimezone(UTC):%Y%m%dT%H%M%SZ}',
        f'DTEND:{meeting.ends_at.astimezone(UTC):%Y%m%dT%H%M%SZ}',
        f'SUMMARY:{_text(meeting.title)}',
        'STATUS:CONFIRMED',
    ]
    if meeting.meet_url:
        lines.append(f'LOCATION:{_text(meeting.meet_url)}')
    lines.extend(['END:VEVENT', 'END:VCALENDAR'])
    return '\r\n'.join(map(_fold, lines)) + '\r\n'
