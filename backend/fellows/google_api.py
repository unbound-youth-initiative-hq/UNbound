import logging
import google.auth.transport.requests
from django.utils import timezone
from django.conf import settings
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from allauth.socialaccount.models import SocialToken
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class GoogleIntegrationError(Exception):
    """A safe error to return when Google cannot fulfil a dashboard request."""


class GoogleConnectionError(GoogleIntegrationError):
    """Raised when the signed-in user needs to connect or reconnect Google."""


def has_google_connection(user):
    return SocialToken.objects.filter(
        account__user=user,
        account__provider='google',
    ).exists()


def get_google_credentials(user):
    token = SocialToken.objects.filter(
        account__user=user,
        account__provider='google',
    ).select_related('app').first()
    if not token:
        raise GoogleConnectionError('Connect your Google account to use this app.')

    app = token.app
    if app:
        client_id = app.client_id
        client_secret = app.secret
    else:
        app_settings = getattr(settings, 'SOCIALACCOUNT_PROVIDERS', {}).get('google', {}).get('APP', {})
        client_id = app_settings.get('client_id')
        client_secret = app_settings.get('secret')

    if not client_id or not client_secret:
        logger.warning('Google OAuth credentials are not configured.')
        raise GoogleConnectionError('Google sign-in is not configured yet.')

    expiry = token.expires_at.replace(tzinfo=None) if token.expires_at else None
    credentials = Credentials(
        token=token.token,
        refresh_token=token.token_secret,
        token_uri='https://oauth2.googleapis.com/token',
        client_id=client_id,
        client_secret=client_secret,
        expiry=expiry,
    )

    if credentials.expired:
        if not credentials.refresh_token:
            raise GoogleConnectionError('Your Google connection has expired. Please reconnect it.')
        try:
            credentials.refresh(google.auth.transport.requests.Request())
        except Exception as exc:
            logger.warning('Google token refresh failed: %s', exc)
            raise GoogleConnectionError('Your Google connection has expired. Please reconnect it.') from exc

        token.token = credentials.token
        token.expires_at = credentials.expiry
        token.save(update_fields=['token', 'expires_at'])

    return credentials


def _google_service(name, version, user):
    return build(name, version, credentials=get_google_credentials(user), cache_discovery=False)


def _api_error(action, exc):
    logger.warning('Google %s request failed: %s', action, exc)
    raise GoogleIntegrationError('Google could not complete that request. Please try again.') from exc


def fetch_calendar_events(user, limit=10):
    try:
        result = _google_service('calendar', 'v3', user).events().list(
            calendarId='primary',
            timeMin=timezone.now().isoformat(),
            maxResults=limit,
            singleEvents=True,
            orderBy='startTime',
            fields='items(id,summary,start,end,location,htmlLink)',
        ).execute()
        return result.get('items', [])
    except GoogleIntegrationError:
        raise
    except Exception as exc:
        _api_error('Calendar', exc)


def fetch_calendar_events_in_range(user, time_min, time_max):
    """Fetch events from user's primary Google Calendar between time_min and time_max."""
    try:
        service = _google_service('calendar', 'v3', user)
        events_result = service.events().list(
            calendarId='primary',
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime',
            fields='items(id,summary,start,end,transparency,location,htmlLink)',
        ).execute()
        return events_result.get('items', [])
    except GoogleIntegrationError:
        raise
    except Exception as exc:
        _api_error('Calendar Range', exc)


def fetch_shared_calendar_events_in_range(user, shared_email=None, time_min=None, time_max=None):
    """Fetch events from shared workspace/cohort calendar between time_min and time_max."""
    cal_id = shared_email or getattr(settings, 'GOOGLE_SHARED_WORKSPACE_EMAIL', 'primary')
    try:
        service = _google_service('calendar', 'v3', user)
        events_result = service.events().list(
            calendarId=cal_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime',
            fields='items(id,summary,start,end,transparency,location)',
        ).execute()
        return events_result.get('items', [])
    except Exception as exc:
        logger.info('Could not fetch shared calendar events (%s): %s', cal_id, exc)
        return []


def sync_user_calendar_availability(user, tz_str='America/Monterrey'):
    """
    Syncs the user's primary Google Calendar events for a 7-day rolling window
    (starting 1 day in the past / yesterday) into MeetingAvailability records.
    """
    from .models import MeetingAvailability

    fellow = getattr(user, 'fellow_profile', None)
    if not fellow:
        raise GoogleIntegrationError('Fellow profile not found.')

    try:
        tz = ZoneInfo(tz_str)
    except Exception:
        tz = ZoneInfo('America/Monterrey')

    now = datetime.now(tz)
    # Start 1 day in the past (yesterday at 00:00:00)
    start_of_window = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_window = start_of_window + timedelta(days=7)

    events = fetch_calendar_events_in_range(
        user,
        time_min=start_of_window.isoformat(),
        time_max=end_of_window.isoformat()
    )

    busy_intervals = []
    for ev in events:
        if ev.get('transparency') == 'transparent':
            continue  # Skip 'free' events

        start_raw = ev.get('start', {})
        end_raw = ev.get('end', {})

        if 'dateTime' in start_raw:
            ev_start = datetime.fromisoformat(start_raw['dateTime'])
        elif 'date' in start_raw:
            ev_start = datetime.strptime(start_raw['date'], '%Y-%m-%d').replace(tzinfo=tz)
        else:
            continue

        if 'dateTime' in end_raw:
            ev_end = datetime.fromisoformat(end_raw['dateTime'])
        elif 'date' in end_raw:
            ev_end = datetime.strptime(end_raw['date'], '%Y-%m-%d').replace(tzinfo=tz)
        else:
            continue

        busy_intervals.append((ev_start, ev_end))

    updated_slots = []
    for day_idx in range(7):
        day_date = start_of_window + timedelta(days=day_idx)
        dow_code = (day_date.weekday() + 1) % 7 # 0 = Sun, 1 = Mon, ..., 6 = Sat

        for h in range(9, 18):
            slot_start = day_date.replace(hour=h, minute=0, second=0, microsecond=0)
            slot_end = slot_start + timedelta(hours=1)

            is_busy = False
            for ev_start, ev_end in busy_intervals:
                if ev_start < slot_end and ev_end > slot_start:
                    is_busy = True
                    break

            slot, _ = MeetingAvailability.objects.update_or_create(
                fellow=fellow,
                day_of_week=dow_code,
                hour=h,
                defaults={'is_available': not is_busy}
            )
            updated_slots.append({
                'day_of_week': slot.day_of_week,
                'hour': slot.hour,
                'is_available': slot.is_available
            })

    return updated_slots


def fetch_user_drive_folders(user, limit=50):
    query = "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    try:
        result = _google_service('drive', 'v3', user).files().list(
            q=query,
            pageSize=limit,
            orderBy='name asc',
            fields='files(id, name, mimeType, modifiedTime, webViewLink)',
        ).execute()
        return result.get('files', [])
    except GoogleIntegrationError:
        raise
    except Exception as exc:
        _api_error('Drive Folders', exc)


def fetch_drive_folder_contents(user, folder_id=None, search='', limit=30):
    query = 'trashed = false'
    if folder_id:
        escaped_id = folder_id.replace("\\", "\\\\").replace("'", "\\'")
        query += f" and '{escaped_id}' in parents"
    if search:
        escaped_search = search.replace("\\", "\\\\").replace("'", "\\'")
        query += f" and name contains '{escaped_search}'"

    try:
        result = _google_service('drive', 'v3', user).files().list(
            q=query,
            pageSize=limit,
            orderBy='folder,modifiedTime desc',
            fields=(
                'files(id, name, mimeType, modifiedTime, webViewLink, iconLink, '
                'thumbnailLink, description, owners(displayName, emailAddress))'
            ),
        ).execute()
        return result.get('files', [])
    except GoogleIntegrationError:
        raise
    except Exception as exc:
        _api_error('Drive Folder Contents', exc)


def fetch_shared_workspace_files(user, shared_email=None, limit=30):
    if shared_email:
        escaped_email = shared_email.replace("\\", "\\\\").replace("'", "\\'")
        query = f"'{escaped_email}' in owners and trashed = false"
    else:
        query = "sharedWithMe = true and trashed = false"

    try:
        result = _google_service('drive', 'v3', user).files().list(
            q=query,
            pageSize=limit,
            orderBy='modifiedTime desc',
            fields=(
                'files(id, name, mimeType, modifiedTime, webViewLink, iconLink, '
                'thumbnailLink, description, owners(displayName, emailAddress))'
            ),
        ).execute()
        return result.get('files', [])
    except GoogleIntegrationError:
        raise
    except Exception as exc:
        _api_error('Shared Workspace Files', exc)


def fetch_google_tasks(user):
    try:
        result = _google_service('tasks', 'v1', user).tasks().list(
            tasklist='@default',
            showCompleted=True,
            showHidden=False,
            maxResults=100,
        ).execute()
        return result.get('items', [])
    except GoogleIntegrationError:
        raise
    except Exception as exc:
        _api_error('Tasks', exc)


def create_google_task(user, title):
    try:
        return _google_service('tasks', 'v1', user).tasks().insert(
            tasklist='@default',
            body={'title': title},
        ).execute()
    except GoogleIntegrationError:
        raise
    except Exception as exc:
        _api_error('Tasks', exc)


def update_google_task(user, task_id, status):
    try:
        return _google_service('tasks', 'v1', user).tasks().patch(
            tasklist='@default',
            task=task_id,
            body={'status': status},
        ).execute()
    except GoogleIntegrationError:
        raise
    except Exception as exc:
        _api_error('Tasks', exc)


def delete_google_task(user, task_id):
    try:
        _google_service('tasks', 'v1', user).tasks().delete(
            tasklist='@default',
            task=task_id,
        ).execute()
    except GoogleIntegrationError:
        raise
    except Exception as exc:
        _api_error('Tasks', exc)


def sync_task_to_google(user, task):
    try:
        if task.google_task_id:
            status = 'completed' if task.status == 'complete' else 'needsAction'
            return update_google_task(user, task.google_task_id, status)
        result = create_google_task(user, task.title)
        task.google_task_id = result['id']
        task.save(update_fields=['google_task_id'])
        return result
    except GoogleIntegrationError:
        return None


def delete_task_from_google(user, google_task_id):
    try:
        delete_google_task(user, google_task_id)
    except GoogleIntegrationError:
        return None