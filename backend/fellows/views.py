from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.db import transaction
from django.db.models import BooleanField, Case, Count, F, Prefetch, Q, Value, When
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_safe
from allauth.socialaccount.models import SocialAccount
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.views import APIView
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .google_api import (
    GoogleConnectionError,
    GoogleIntegrationError,
    create_google_task,
    delete_google_task,
    fetch_calendar_events,
    fetch_calendar_events_in_range,
    fetch_user_drive_folders,
    fetch_drive_folder_contents,
    fetch_shared_workspace_files,
    fetch_google_tasks,
    has_google_connection,
    sync_task_to_google,
    delete_task_from_google,
    update_google_task,
    sync_user_calendar_availability,
    fetch_shared_calendar_events_in_range,
)
from .artwork import TASK_ICONS
from .meeting_timezones import meeting_timezone_choices
from .models import (
    MeetingAvailability, Task, Fellow, Badge, FellowBadge, InviteCode, SDG, Cohort, CohortDriveLink,
    AvailabilityRequest, ConfirmedMeeting, Phase, SharedDriveResource, availability_task_visibility_filter,
)
from .calendar_export import meeting_calendar
from .forms import DrivePinForm
from .serializers import MeetingAvailabilitySerializer, TaskSerializer, AvailabilityRequestSerializer
from .badges_engine import badge_rank_title, evaluate_and_sync_badges


def google_account_details(user):
    account = SocialAccount.objects.filter(user=user, provider='google').first()
    data = account.extra_data if account else {}
    name = data.get('name') or user.get_full_name() or user.email or user.username
    return {
        # A Google identity remains connected without storing data API tokens.
        'connected': account is not None,
        'name': name,
        'email': data.get('email') or user.email,
        'picture': data.get('picture', ''),
    }


@login_required(login_url='account_login')
def dashboard_view(request, drive=False):
    fellow = getattr(request.user, 'fellow_profile', None)
    if fellow is None:
        return redirect('register_code')
    pin_form = DrivePinForm()
    if drive and request.method == 'POST':
        if fellow.cohort_id is None:
            raise DjangoPermissionDenied
        pin_form = DrivePinForm(request.POST)
        if pin_form.is_valid():
            with transaction.atomic():
                # Serialize retries from this fellow and check their current cohort.
                member = Fellow.objects.select_for_update().get(pk=fellow.pk)
                if member.cohort_id != fellow.cohort_id:
                    raise DjangoPermissionDenied
                _, created = CohortDriveLink.objects.get_or_create(
                    cohort_id=member.cohort_id,
                    pinned_by=member,
                    url=pin_form.cleaned_data['url'],
                    defaults={'title': pin_form.cleaned_data['title']},
                )
            messages.success(request, 'Pinned to your cohort.' if created else 'You’ve already pinned this link.')
            return redirect('dashboard-drive')

    links = CohortDriveLink.objects.filter(cohort_id=fellow.cohort_id, is_published=True)
    shared_resources = SharedDriveResource.objects.none()
    if fellow.cohort_id:
        shared_resources = SharedDriveResource.objects.filter(is_published=True).filter(
            Q(audience=SharedDriveResource.Audience.ALL)
            | Q(audience=SharedDriveResource.Audience.SELECTED, cohorts=fellow.cohort_id)
        ).distinct()
    return render(request, 'fellow-dashboard.html', {
        'google_account': google_account_details(request.user),
        'google_integrations_enabled': settings.GOOGLE_INTEGRATIONS_ENABLED,
        'drive_links': [*shared_resources, *links.filter(pinned_by__isnull=True)],
        'drive_pins': links.filter(pinned_by__isnull=False).order_by('-pk'),
        'drive_active': drive,
        'drive_pin_form': pin_form if fellow.cohort_id else None,
        'fellow_id': fellow.pk,
        'confirmed_meetings': confirmed_meetings_for(fellow).filter(ends_at__gt=timezone.now()),
        'accent_palette': fellow.accent_palette,
        'meeting_timezone': fellow.meeting_timezone,
        'meeting_timezones': meeting_timezone_choices(),
        'task_icons': TASK_ICONS,
    })


def confirmed_meetings_for(fellow):
    return ConfirmedMeeting.objects.filter(is_published=True, cohort_id=fellow.cohort_id)


@login_required(login_url='account_login')
@require_safe
@never_cache
def download_meeting(request, pk):
    fellow = getattr(request.user, 'fellow_profile', None)
    meetings = confirmed_meetings_for(fellow) if fellow else ConfirmedMeeting.objects.none()
    meeting = get_object_or_404(meetings, pk=pk)
    return HttpResponse(
        meeting_calendar(meeting),
        content_type='text/calendar; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="unbound-meeting-{meeting.pk}.ics"'},
    )


@login_required(login_url='account_login')
@require_POST
def remove_drive_pin(request, pk):
    pin = get_object_or_404(
        CohortDriveLink, pk=pk, pinned_by__user=request.user, cohort_id=F('pinned_by__cohort_id'),
    )
    pin.delete()
    messages.success(request, 'Link unpinned.')
    return redirect('dashboard-drive')


def register_code_view(request):
    """View where new fellows enter their invitation code before logging in with Google."""
    if request.user.is_authenticated and Fellow.objects.filter(user=request.user).exists():
        return redirect('dashboard')
    error = None
    if request.method == 'POST':
        code_input = request.POST.get('invite_code', '').strip().upper()
        if not code_input:
            error = "Please enter an invitation code."
        else:
            try:
                invite = InviteCode.objects.get(code=code_input)
                valid, msg = invite.is_valid()
                if valid:
                    request.session['verified_invite_code_id'] = invite.id
                    return redirect('/accounts/google/login/?process=connect&next=/dashboard/' if request.user.is_authenticated else '/accounts/google/login/')
                else:
                    error = msg
            except InviteCode.DoesNotExist:
                error = "Invalid invitation code. Please reach out to the Fellowship Execs for access."

    return render(request, 'account/register_code.html', {'error': error})


class GoogleConnectionAPIView(APIView):
    """Shared connection handling for all Google-backed endpoints."""

    def connection_response(self, user):
        if not settings.GOOGLE_INTEGRATIONS_ENABLED:
            return google_integrations_disabled_response()
        if has_google_connection(user):
            return None
        return Response({
            'connected': False,
            'detail': 'Connect your Google account to use this app.',
        }, status=status.HTTP_403_FORBIDDEN)

    def integration_error_response(self, exc):
        if isinstance(exc, GoogleConnectionError):
            return Response({
                'connected': False,
                'detail': str(exc),
            }, status=status.HTTP_403_FORBIDDEN)
        return Response({
            'connected': True,
            'detail': str(exc),
        }, status=status.HTTP_502_BAD_GATEWAY)


def google_integrations_disabled_response():
    return Response({
        'enabled': False,
        'code': 'google_integrations_disabled',
        'detail': 'Google Calendar, Drive and Tasks integrations are not enabled. Use UNbound tasks and manual availability.',
    }, status=status.HTTP_403_FORBIDDEN)


class GoogleAccountView(APIView):
    def get(self, request, *args, **kwargs):
        return Response(google_account_details(request.user))


class GoogleCalendarEventsView(GoogleConnectionAPIView):
    def get(self, request, *args, **kwargs):
        disconnected = self.connection_response(request.user)
        if disconnected:
            return disconnected
        try:
            time_min = request.query_params.get('time_min')
            time_max = request.query_params.get('time_max')
            if bool(time_min) != bool(time_max):
                return Response(
                    {'connected': True, 'detail': 'Both time_min and time_max are required for a date range.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if time_min and time_max:
                try:
                    range_start = datetime.fromisoformat(time_min.replace('Z', '+00:00'))
                    range_end = datetime.fromisoformat(time_max.replace('Z', '+00:00'))
                except ValueError:
                    return Response(
                        {'connected': True, 'detail': 'Calendar date ranges must use ISO 8601 timestamps.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if (
                    range_start.tzinfo is None or range_start.utcoffset() is None
                    or range_end.tzinfo is None or range_end.utcoffset() is None
                    or range_end <= range_start
                    or range_end - range_start > timedelta(days=366)
                ):
                    return Response(
                        {'connected': True, 'detail': 'The calendar date range is invalid or too long.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                events = fetch_calendar_events_in_range(request.user, time_min, time_max)
            else:
                events = fetch_calendar_events(request.user)
            return Response({'connected': True, 'events': events})
        except GoogleIntegrationError as exc:
            return self.integration_error_response(exc)


class GoogleDrivePersonalFilesView(GoogleConnectionAPIView):
    def get(self, request, *args, **kwargs):
        disconnected = self.connection_response(request.user)
        if disconnected:
            return disconnected

        fellow = getattr(request.user, 'fellow_profile', None)
        folder_id = request.query_params.get('folder_id') or (fellow.selected_drive_folder_id if fellow else None)

        try:
            files = fetch_drive_folder_contents(request.user, folder_id=folder_id, search=request.query_params.get('q', '').strip())
            folder_name = (fellow.selected_drive_folder_name if (fellow and fellow.selected_drive_folder_id) else None)
            return Response({
                'status': 'success',
                'connected': True,
                'selected_folder_id': folder_id or '',
                'selected_folder_name': folder_name or '',
                'files': files
            })
        except GoogleIntegrationError as exc:
            return self.integration_error_response(exc)


class GoogleDriveSharedFilesView(GoogleConnectionAPIView):
    def get(self, request, *args, **kwargs):
        disconnected = self.connection_response(request.user)
        if disconnected:
            return disconnected

        shared_email = getattr(settings, 'GOOGLE_SHARED_WORKSPACE_EMAIL', 'workspace@unbound.org')
        try:
            files = fetch_shared_workspace_files(request.user, shared_email=shared_email)
            return Response({
                'status': 'success',
                'connected': True,
                'shared_email': shared_email,
                'files': files
            })
        except GoogleIntegrationError as exc:
            return self.integration_error_response(exc)


class GoogleDriveFoldersView(GoogleConnectionAPIView):
    def get(self, request, *args, **kwargs):
        disconnected = self.connection_response(request.user)
        if disconnected:
            return disconnected
        try:
            folders = fetch_user_drive_folders(request.user)
            return Response({
                'status': 'success',
                'connected': True,
                'folders': folders
            })
        except GoogleIntegrationError as exc:
            return self.integration_error_response(exc)


class GoogleDriveSetFolderView(GoogleConnectionAPIView):
    def post(self, request, *args, **kwargs):
        disconnected = self.connection_response(request.user)
        if disconnected:
            return disconnected

        raw_folder_input = str(request.data.get('folder_id', '')).strip()
        folder_id = raw_folder_input
        if 'drive.google.com' in raw_folder_input and 'folders/' in raw_folder_input:
            folder_id = raw_folder_input.split('folders/')[-1].split('?')[0].split('/')[0]

        folder_name = str(request.data.get('folder_name', '')).strip()

        fellow = getattr(request.user, 'fellow_profile', None)
        if fellow:
            fellow.selected_drive_folder_id = folder_id
            if folder_name:
                fellow.selected_drive_folder_name = folder_name
            elif not folder_id:
                fellow.selected_drive_folder_name = ''
            fellow.save()

        return Response({
            'status': 'success',
            'message': 'Folder updated successfully.',
            'folder_id': folder_id
        })


class GoogleTasksView(GoogleConnectionAPIView):
    def get(self, request, *args, **kwargs):
        disconnected = self.connection_response(request.user)
        if disconnected:
            return disconnected
        try:
            return Response({'connected': True, 'tasks': fetch_google_tasks(request.user)})
        except GoogleIntegrationError as exc:
            return self.integration_error_response(exc)

    def post(self, request, *args, **kwargs):
        disconnected = self.connection_response(request.user)
        if disconnected:
            return disconnected
        title = str(request.data.get('title', '')).strip()
        if not title:
            return Response({'detail': 'A task title is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if len(title) > 1024:
            return Response({'detail': 'A task title must be 1024 characters or fewer.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            task = create_google_task(request.user, title)
            return Response({'connected': True, 'task': task}, status=status.HTTP_201_CREATED)
        except GoogleIntegrationError as exc:
            return self.integration_error_response(exc)


class GoogleTaskDetailView(GoogleConnectionAPIView):
    def patch(self, request, task_id, *args, **kwargs):
        disconnected = self.connection_response(request.user)
        if disconnected:
            return disconnected
        task_status = request.data.get('status')
        if task_status not in {'needsAction', 'completed'}:
            return Response({
                'detail': 'Status must be needsAction or completed.',
            }, status=status.HTTP_400_BAD_REQUEST)
        try:
            task = update_google_task(request.user, task_id, task_status)
            return Response({'connected': True, 'task': task})
        except GoogleIntegrationError as exc:
            return self.integration_error_response(exc)

    def delete(self, request, task_id, *args, **kwargs):
        disconnected = self.connection_response(request.user)
        if disconnected:
            return disconnected
        try:
            delete_google_task(request.user, task_id)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except GoogleIntegrationError as exc:
            return self.integration_error_response(exc)


class CohortSDGsAPIView(APIView):
    """API endpoint allowing users/fellows to view and update their cohort's selected UN goals (SDGs)."""

    def get(self, request, *args, **kwargs):
        if not hasattr(request.user, 'fellow_profile'):
            return Response({'status': 'error', 'detail': 'Fellow profile missing.'}, status=status.HTTP_400_BAD_REQUEST)

        fellow = request.user.fellow_profile

        cohort = fellow.cohort
        selected_codes = set(cohort.selected_sdgs.values_list('code', flat=True)) if cohort else set()

        all_sdgs = SDG.objects.all().order_by('code')
        sdgs_list = [
            {
                'code': s.code,
                'name': s.name,
                'color': s.color,
                'selected': s.code in selected_codes
            }
            for s in all_sdgs
        ]

        return Response({
            'status': 'success',
            'cohort_name': cohort.name if cohort else '',
            'sdgs': sdgs_list
        })

    def post(self, request, *args, **kwargs):
        if not hasattr(request.user, 'fellow_profile'):
            return Response({'status': 'error', 'detail': 'Fellow profile missing.'}, status=status.HTTP_400_BAD_REQUEST)

        fellow = request.user.fellow_profile
        cohort = fellow.cohort

        if not cohort:
            return Response({'status': 'error', 'detail': 'You are not currently assigned to a cohort.'}, status=status.HTTP_400_BAD_REQUEST)


        raw_codes = request.data.get('sdg_codes', [])
        if not isinstance(raw_codes, list):
            return Response({'status': 'error', 'detail': 'sdg_codes must be a list.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            codes = [int(c) for c in raw_codes]
        except (ValueError, TypeError):
            return Response({'status': 'error', 'detail': 'Invalid SDG codes provided.'}, status=status.HTTP_400_BAD_REQUEST)

        matching_sdgs = SDG.objects.filter(code__in=codes)
        cohort.selected_sdgs.set(matching_sdgs)

        selected_data = [
            {
                'code': s.code,
                'name': s.name,
                'color': s.color
            }
            for s in matching_sdgs.order_by('code')
        ]

        return Response({
            'status': 'success',
            'message': 'Cohort SDGs updated successfully.',
            'sdgs': selected_data
        })


@login_required(login_url='account_login')
@require_safe
def badge_icon(request, pk):
    badge = get_object_or_404(Badge.objects.only('icon_png').exclude(icon_png=b''), pk=pk)
    return HttpResponse(bytes(badge.icon_png), content_type='image/png')


class BadgesAPIView(APIView):
    def get(self, request, *args, **kwargs):
        if not hasattr(request.user, 'fellow_profile'):
            return Response({'status': 'error', 'detail': 'Fellow profile missing.'}, status=status.HTTP_400_BAD_REQUEST)

        fellow = request.user.fellow_profile
        evaluate_and_sync_badges(fellow, from_read=True)

        fellow_badges = list(FellowBadge.objects.filter(fellow=fellow).select_related('badge')
            .defer('badge__icon_png').annotate(custom_icon=Case(
                When(badge__icon_png=b'', then=Value(False)),
                default=Value(True), output_field=BooleanField(),
            )).order_by('badge__order'))
        earned_count = sum(record.earned for record in fellow_badges)
        total_count = len(fellow_badges)

        badges_data = []
        for fb in fellow_badges:
            b = fb.badge
            badges_data.append({
                'id': b.id,
                'name': b.name,
                'description': b.description,
                'color': b.color,
                'icon_class': b.icon_class,
                'artwork': b.artwork,
                'has_custom_icon': fb.custom_icon,
                'earned': fb.earned,
                'progress': fb.progress,
                'earned_at': fb.earned_at,
            })

        return Response({
            'status': 'success',
            'level_title': badge_rank_title(earned_count),
            'earned_count': earned_count,
            'total_count': total_count,
            'xp_points': fellow.xp_points,
            'badges': badges_data
        })


class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer

    def get_queryset(self):
        if not hasattr(self.request.user, 'fellow_profile'):
            return Task.objects.none()
        fellow = self.request.user.fellow_profile

        if fellow.cohort:
            qs = Task.objects.filter(
                Q(assigned_to=fellow) |
                (Q(scope=Task.Scope.TEAM) & Q(cohort=fellow.cohort))
            )
        else:
            qs = Task.objects.filter(assigned_to=fellow)

        return qs.filter(
            availability_task_visibility_filter(fellow)
        ).order_by('-created_at')

    def perform_create(self, serializer):
        fellow = getattr(self.request.user, 'fellow_profile', None)
        if fellow is None:
            raise PermissionDenied('A fellow profile is required to create tasks.')
        scope = serializer.validated_data.get('scope', Task.Scope.PERSONAL)
        icon = serializer.validated_data.get('icon') or ('fa-pen-to-square' if scope == Task.Scope.TEAM else 'fa-check')
        color = serializer.validated_data.get('color') or ('#00B4D8' if scope == Task.Scope.TEAM else '#e0a009')

        with transaction.atomic():
            task = serializer.save(
                assigned_to=fellow,
                cohort=fellow.cohort,
                source=Task.Source.SELF,
                icon=icon,
                color=color,
            )
            if task.status == Task.Status.COMPLETE:
                self._refresh_task_progress(task)
        self._sync_google_mirrors(task)

    def _refresh_task_progress(self, task):
        if Badge.objects.filter(trigger_type=Badge.TriggerType.TASK_COUNT).exists():
            for fellow in task.affected_fellows():
                evaluate_and_sync_badges(fellow)

    def _sync_google_mirrors(self, task):
        if not settings.GOOGLE_INTEGRATIONS_ENABLED:
            return
        # Each member's Google task is owned by that member's Google account.
        users = {self.request.user.pk: self.request.user}
        for link in task.google_links.select_related('user'):
            users[link.user_id] = link.user
        for user in users.values():
            if has_google_connection(user):
                sync_task_to_google(user, task)

    def update(self, request, *args, **kwargs):
        with transaction.atomic():
            tasks = self.filter_queryset(self.get_queryset()).select_for_update(of=('self',))
            task = get_object_or_404(tasks, pk=kwargs['pk'])
            self.check_object_permissions(request, task)
            was_complete = task.status == Task.Status.COMPLETE
            serializer = self.get_serializer(task, data=request.data, partial=kwargs.get('partial', False))
            serializer.is_valid(raise_exception=True)
            task = serializer.save()
            if was_complete != (task.status == Task.Status.COMPLETE):
                self._refresh_task_progress(task)
        self._sync_google_mirrors(task)
        return Response(serializer.data)

    def perform_destroy(self, instance):
        if not instance.can_manage(self.request.user):
            raise PermissionDenied('Only the creator can delete a self-created task. Staff manage UNbound assignments.')
        mirrors = {}
        if settings.GOOGLE_INTEGRATIONS_ENABLED:
            mirrors = {link.user_id: (link.user, link.google_task_id) for link in instance.google_links.select_related('user')}
            if instance.scope == Task.Scope.PERSONAL and instance.google_task_id and instance.assigned_to_id:
                owner = instance.assigned_to.user
                mirrors.setdefault(owner.pk, (owner, instance.google_task_id))
        with transaction.atomic():
            fellows = []
            if instance.status == Task.Status.COMPLETE and Badge.objects.filter(trigger_type=Badge.TriggerType.TASK_COUNT).exists():
                fellows = list(instance.affected_fellows())
            instance.delete()
            for fellow in fellows:
                evaluate_and_sync_badges(fellow)
        for user, google_task_id in mirrors.values():
            if google_task_id and has_google_connection(user):
                delete_task_from_google(user, google_task_id)


class MeetingAvailabilityViewSet(viewsets.ModelViewSet):
    serializer_class = MeetingAvailabilitySerializer

    def get_queryset(self):
        if not hasattr(self.request.user, 'fellow_profile'):
            return MeetingAvailability.objects.none()
        fellow = self.request.user.fellow_profile
        slots = MeetingAvailability.objects.filter(fellow=fellow)
        req_id = self.request.query_params.get('request_id')
        if req_id:
            try:
                avail_request = AvailabilityRequest.objects.filter(
                    pk=int(req_id),
                    is_active=True,
                ).first()
            except (TypeError, ValueError):
                avail_request = None
            if not avail_request or not avail_request.target_fellows().filter(pk=fellow.pk).exists():
                return MeetingAvailability.objects.none()
            return slots.filter(availability_request=avail_request)
        return slots.filter(
            availability_task_visibility_filter(fellow)
        )

    def perform_create(self, serializer):
        from .availability import request_for_fellow, mark_response_draft
        fellow = self.request.user.fellow_profile
        with transaction.atomic():
            meeting = request_for_fellow(fellow, serializer.validated_data['availability_request'].pk, lock=True)
            serializer.save(fellow=fellow)
            mark_response_draft(meeting, fellow)

    def perform_update(self, serializer):
        from .availability import request_for_fellow, mark_response_draft
        fellow = self.request.user.fellow_profile
        with transaction.atomic():
            meeting = request_for_fellow(fellow, serializer.instance.availability_request_id, lock=True)
            serializer.save()
            mark_response_draft(meeting, fellow)

    def perform_destroy(self, instance):
        from .availability import request_for_fellow, mark_response_draft
        fellow = self.request.user.fellow_profile
        with transaction.atomic():
            meeting = request_for_fellow(fellow, instance.availability_request_id, lock=True)
            instance.delete()
            mark_response_draft(meeting, fellow)

    @action(detail=False, methods=['get'], url_path='requests')
    def requests(self, request):
        """Returns all active WhenBound availability requests relevant to the current fellow."""
        if not hasattr(request.user, 'fellow_profile'):
            return Response({'detail': 'Fellow profile missing.'}, status=status.HTTP_400_BAD_REQUEST)

        fellow = request.user.fellow_profile
        if fellow.role != Fellow.Role.FELLOW or not request.user.is_active:
            return Response({'status': 'success', 'requests': []})

        qs = AvailabilityRequest.objects.filter(is_active=True)
        if fellow.cohort:
            qs = qs.filter(Q(assign_to_all=True) | Q(cohort=fellow.cohort) | Q(cohort__isnull=True))
        else:
            qs = qs.filter(Q(assign_to_all=True) | Q(cohort__isnull=True))

        meetings = list(qs.order_by('-created_at'))
        existing = dict(Task.objects.filter(
            assigned_to=fellow, availability_request__in=meetings,
        ).values_list('availability_request_id', 'cohort_id'))
        for meeting in meetings:
            if meeting.pk not in existing or existing[meeting.pk] != fellow.cohort_id:
                meeting.create_tasks_for_fellows(fellow=fellow)
        serializer = AvailabilityRequestSerializer(meetings, many=True, context={'request': request})
        return Response({'status': 'success', 'requests': serializer.data})

    @action(detail=False, methods=['post'], url_path='bulk-save')
    def bulk_save(self, request):
        if not hasattr(request.user, 'fellow_profile'):
            return Response({'detail': 'Fellow profile missing.'}, status=status.HTTP_400_BAD_REQUEST)

        from .availability import submit_availability
        fellow = request.user.fellow_profile
        with transaction.atomic():
            records = submit_availability(fellow, request.data.get('request_id'), request.data.get('slots'))
            if Badge.objects.filter(trigger_type__in=[Badge.TriggerType.AVAILABILITY, Badge.TriggerType.TASK_COUNT]).exists():
                evaluate_and_sync_badges(fellow)
        return Response({'status': 'success', 'is_completed': True, 'slots': self.get_serializer(records, many=True).data})

    @action(detail=False, methods=['post'], url_path='sync-google')
    def sync_google(self, request):
        if not settings.GOOGLE_INTEGRATIONS_ENABLED:
            return google_integrations_disabled_response()
        if not has_google_connection(request.user):
            return Response({
                'connected': False,
                'detail': 'Connect your Google account to sync calendar availability.'
            }, status=status.HTTP_403_FORBIDDEN)

        tz_str = request.data.get('timezone', 'America/Monterrey')
        req_id = request.data.get('request_id')
        fellow = getattr(request.user, 'fellow_profile', None)
        if req_id:
            try:
                avail_request = AvailabilityRequest.objects.filter(
                    pk=int(req_id),
                    is_active=True,
                ).first()
            except (TypeError, ValueError):
                avail_request = None
            if (
                not avail_request
                or not fellow
                or fellow.role != Fellow.Role.FELLOW
                or not avail_request.target_fellows().filter(pk=fellow.pk).exists()
            ):
                return Response(
                    {'detail': 'Active availability request not found.'},
                    status=status.HTTP_404_NOT_FOUND,
                )
        try:
            slots = sync_user_calendar_availability(request.user, tz_str=tz_str, request_id=req_id)
            if hasattr(request.user, 'fellow_profile'):
                evaluate_and_sync_badges(request.user.fellow_profile)
            return Response({'connected': True, 'status': 'success', 'is_completed': True, 'slots': slots})
        except GoogleIntegrationError as exc:
            return Response({'connected': True, 'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

    @action(detail=False, methods=['get'], url_path='group-availability')
    def group_availability(self, request):
        if not hasattr(request.user, 'fellow_profile'):
            return Response({'detail': 'Fellow profile missing.'}, status=status.HTTP_400_BAD_REQUEST)

        fellow = request.user.fellow_profile
        req_id = request.query_params.get('request_id')
        tz_str = request.query_params.get('timezone', 'America/Monterrey')

        avail_request = None
        if req_id:
            try:
                avail_request = AvailabilityRequest.objects.filter(
                    pk=int(req_id),
                    is_active=True,
                ).first()
            except (TypeError, ValueError):
                avail_request = None
            if (
                not avail_request
                or fellow.role != Fellow.Role.FELLOW
                or not avail_request.target_fellows().filter(pk=fellow.pk).exists()
            ):
                return Response(
                    {'detail': 'Active availability request not found.'},
                    status=status.HTTP_404_NOT_FOUND,
                )

        try:
            tz = ZoneInfo(tz_str)
        except Exception:
            tz = ZoneInfo('America/Monterrey')

        shared_email = getattr(settings, 'GOOGLE_SHARED_WORKSPACE_EMAIL', 'primary')

        if avail_request:
            tz = ZoneInfo(settings.TIME_ZONE)
            active_fellows = Fellow.objects.filter(
                role=Fellow.Role.FELLOW,
                user__is_active=True,
            ).select_related('user')
            if not avail_request.assign_to_all and avail_request.cohort_id:
                cohort_fellows = avail_request.target_fellows()
            elif fellow.cohort_id:
                cohort_fellows = active_fellows.filter(cohort_id=fellow.cohort_id)
            else:
                cohort_fellows = avail_request.target_fellows()

            total_members = max(1, cohort_fellows.count())

            avail_qs = MeetingAvailability.objects.filter(
                availability_request=avail_request,
                fellow__in=cohort_fellows,
                is_available=True
            ).select_related('fellow__user')

            start_d = avail_request.start_date
            end_d = avail_request.end_date
            num_days = (end_d - start_d).days + 1
            dates_list = [start_d + timedelta(days=i) for i in range(num_days)]
            start_hour = avail_request.start_hour
            end_hour = avail_request.end_hour

            matrix_data = {(d.isoformat(), h): [] for d in dates_list for h in range(start_hour, end_hour)}
            for record in avail_qs:
                if record.date:
                    key = (record.date.isoformat(), record.hour)
                    if key in matrix_data:
                        name = record.fellow.user.get_full_name() or record.fellow.user.username
                        matrix_data[key].append(name)

            shared_events_grid = {}
            if has_google_connection(request.user):
                s_window = datetime.combine(start_d, datetime.min.time(), tzinfo=tz)
                e_window = datetime.combine(end_d + timedelta(days=1), datetime.min.time(), tzinfo=tz)
                shared_events = fetch_shared_calendar_events_in_range(
                    request.user,
                    shared_email=shared_email,
                    time_min=s_window.isoformat(),
                    time_max=e_window.isoformat()
                )
                for ev in shared_events:
                    if ev.get('transparency') == 'transparent':
                        continue
                    start_raw = ev.get('start', {})
                    end_raw = ev.get('end', {})
                    if 'dateTime' in start_raw:
                        ev_s = datetime.fromisoformat(start_raw['dateTime'])
                    elif 'date' in start_raw:
                        ev_s = datetime.strptime(start_raw['date'], '%Y-%m-%d').replace(tzinfo=tz)
                    else:
                        continue
                    if 'dateTime' in end_raw:
                        ev_e = datetime.fromisoformat(end_raw['dateTime'])
                    elif 'date' in end_raw:
                        ev_e = datetime.strptime(end_raw['date'], '%Y-%m-%d').replace(tzinfo=tz)
                    else:
                        continue

                    for day_date in dates_list:
                        day_iso = day_date.isoformat()
                        for h in range(start_hour, end_hour):
                            slot_start = datetime.combine(day_date, datetime.min.time(), tzinfo=tz).replace(hour=h)
                            slot_end = slot_start + timedelta(hours=1)
                            if ev_s < slot_end and ev_e > slot_start:
                                shared_events_grid[(day_iso, h)] = ev.get('summary', 'Shared Group Event')

            formatted_matrix = []
            today_date = datetime.now(tz).date()
            for (date_iso, h), available_names in matrix_data.items():
                count = len(available_names)
                pct = round((count / total_members) * 100) if total_members > 0 else 0
                formatted_matrix.append({
                    'date': date_iso,
                    'hour': h,
                    'available_count': count,
                    'total_members': total_members,
                    'percentage': pct,
                    'available_members': available_names,
                    'group_event': shared_events_grid.get((date_iso, h))
                })

            dates_info = [
                {
                    'date': d.isoformat(),
                    'dayName': d.strftime('%a'),
                    'monthName': d.strftime('%b'),
                    'dayNum': d.day,
                    'dayOfWeek': (d.weekday() + 1) % 7,
                    'isToday': (d == today_date)
                }
                for d in dates_list
            ]

            return Response({
                'status': 'success',
                'is_request': True,
                'request': AvailabilityRequestSerializer(avail_request, context={'request': request}).data,
                'total_members': total_members,
                'dates': dates_info,
                'matrix': formatted_matrix,
                'start_hour': start_hour,
                'end_hour': end_hour
            })

        # Legacy 7-day rolling window fallback uses only current fellows and
        # legacy slots; request-specific responses stay with their request.
        cohort_fellows = Fellow.objects.filter(
            role=Fellow.Role.FELLOW,
            user__is_active=True,
        ).select_related('user')
        if fellow.cohort_id:
            cohort_fellows = cohort_fellows.filter(cohort_id=fellow.cohort_id)
        elif fellow.chapter_id:
            cohort_fellows = cohort_fellows.filter(chapter_id=fellow.chapter_id)

        total_members = max(1, cohort_fellows.count())
        avail_qs = MeetingAvailability.objects.filter(
            fellow__in=cohort_fellows,
            availability_request__isnull=True,
            is_available=True
        ).select_related('fellow__user')

        matrix_data = {(d, h): [] for d in range(7) for h in range(9, 18)}
        for record in avail_qs:
            key = (record.day_of_week, record.hour)
            if key in matrix_data:
                name = record.fellow.user.get_full_name() or record.fellow.user.username
                matrix_data[key].append(name)

        shared_events_grid = {}
        if has_google_connection(request.user):
            now = datetime.now(tz)
            s_window = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            e_window = s_window + timedelta(days=7)

            shared_events = fetch_shared_calendar_events_in_range(
                request.user,
                shared_email=shared_email,
                time_min=s_window.isoformat(),
                time_max=e_window.isoformat()
            )

            for ev in shared_events:
                if ev.get('transparency') == 'transparent':
                    continue
                start_raw = ev.get('start', {})
                end_raw = ev.get('end', {})
                if 'dateTime' in start_raw:
                    ev_s = datetime.fromisoformat(start_raw['dateTime'])
                elif 'date' in start_raw:
                    ev_s = datetime.strptime(start_raw['date'], '%Y-%m-%d').replace(tzinfo=tz)
                else:
                    continue
                if 'dateTime' in end_raw:
                    ev_e = datetime.fromisoformat(end_raw['dateTime'])
                elif 'date' in end_raw:
                    ev_e = datetime.strptime(end_raw['date'], '%Y-%m-%d').replace(tzinfo=tz)
                else:
                    continue

                for i in range(7):
                    day_date = s_window + timedelta(days=i)
                    dow_code = (day_date.weekday() + 1) % 7
                    for h in range(9, 18):
                        slot_start = day_date.replace(hour=h, minute=0, second=0, microsecond=0)
                        slot_end = slot_start + timedelta(hours=1)
                        if ev_s < slot_end and ev_e > slot_start:
                            shared_events_grid[(dow_code, h)] = ev.get('summary', 'Shared Group Event')

        formatted_matrix = []
        for (day_of_week, h), available_names in matrix_data.items():
            count = len(available_names)
            pct = round((count / total_members) * 100) if total_members > 0 else 0
            formatted_matrix.append({
                'day_of_week': day_of_week,
                'hour': h,
                'available_count': count,
                'total_members': total_members,
                'percentage': pct,
                'available_members': available_names,
                'group_event': shared_events_grid.get((day_of_week, h))
            })

        return Response({
            'status': 'success',
            'is_request': False,
            'total_members': total_members,
            'matrix': formatted_matrix
        })


class DashboardPreferencesAPIView(APIView):
    """Read and update the signed-in fellow's small set of dashboard preferences."""

    def get(self, request, *args, **kwargs):
        fellow = getattr(request.user, 'fellow_profile', None)
        if fellow is None:
            return Response({'status': 'error', 'detail': 'Fellow profile missing.'}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'status': 'success', 'accent_palette': fellow.accent_palette, 'meeting_timezone': fellow.meeting_timezone,
        })

    def patch(self, request, *args, **kwargs):
        fellow = getattr(request.user, 'fellow_profile', None)
        if fellow is None:
            return Response({'status': 'error', 'detail': 'Fellow profile missing.'}, status=status.HTTP_400_BAD_REQUEST)

        updates = {}
        zones = dict(Fellow._meta.get_field('meeting_timezone').flatchoices)
        for field, choices, error in (
            ('accent_palette', Fellow.AccentPalette.values, 'Choose one of the available accent palettes.'),
            ('meeting_timezone', zones, 'Choose one of the available meeting time zones.'),
        ):
            if field in request.data:
                value = request.data[field]
                if not isinstance(value, str) or value not in choices:
                    return Response({'status': 'error', 'detail': error}, status=status.HTTP_400_BAD_REQUEST)
                updates[field] = value
        if not updates:
            return Response({'status': 'error', 'detail': 'Choose a preference to update.'}, status=status.HTTP_400_BAD_REQUEST)
        for field, value in updates.items():
            setattr(fellow, field, value)
        fellow.save(update_fields=updates)
        return Response({
            'status': 'success', 'accent_palette': fellow.accent_palette, 'meeting_timezone': fellow.meeting_timezone,
        })


class DashboardOverviewAPIView(APIView):
    def get(self, request, *args, **kwargs):
        if not hasattr(request.user, 'fellow_profile'):
            return Response({'status': 'error', 'detail': 'Fellow profile missing.'}, status=status.HTTP_400_BAD_REQUEST)

        fellow = request.user.fellow_profile
        user = request.user

        first_name = user.first_name or (user.get_full_name().split()[0] if user.get_full_name() else user.email.split('@')[0])

        cohort = fellow.cohort
        cohort_name = f"Cohort {cohort.name}" if cohort else ""
        current_phase = cohort.current_phase if cohort else ""
        project_name = cohort.project_name if cohort else ""
        project_description = cohort.project_description if cohort else ""

        if fellow.chapter:
            chapter_str = f"{fellow.chapter.name}, {fellow.chapter.country_code}"
        else:
            chapter_str = ""

        team_members = []
        if cohort:
            cohort_fellows = Fellow.objects.filter(cohort=cohort, user__is_active=True).select_related('user').prefetch_related(
                Prefetch('user__socialaccount_set', queryset=SocialAccount.objects.filter(provider='google').order_by('pk'),
                         to_attr='google_accounts'),
            )
        else:
            cohort_fellows = Fellow.objects.none()

        for cf in cohort_fellows:
            accounts = cf.user.google_accounts
            picture = accounts[0].extra_data.get('picture', '') if accounts else ''
            member_name = cf.user.get_full_name() or cf.user.username or cf.user.email
            initials = "".join([part[0].upper() for part in member_name.split()[:2]]) if member_name else "F"
            
            team_members.append({
                'id': cf.id,
                'name': member_name,
                'email': cf.user.email,
                'role': cf.get_role_display(),
                'picture': picture,
                'initials': initials,
                'is_current_user': (cf.id == fellow.id)
            })

        sdgs_data = []
        if cohort:
            sdgs_data = list(cohort.selected_sdgs.values('code', 'name', 'color'))
        if cohort:
            tasks_qs = Task.objects.filter(
                Q(assigned_to=fellow) | (Q(scope=Task.Scope.TEAM) & Q(cohort=cohort))
            )
        else:
            tasks_qs = Task.objects.filter(assigned_to=fellow)

        tasks_qs = tasks_qs.filter(
            availability_task_visibility_filter(fellow)
        )
        unfinished = tasks_qs.exclude(status=Task.Status.COMPLETE)
        counts = tasks_qs.aggregate(total=Count('pk'), completed=Count('pk', filter=Q(status=Task.Status.COMPLETE)))
        total_tasks, completed_tasks = counts['total'], counts['completed']
        open_tasks = total_tasks - completed_tasks
        now = timezone.localtime()
        today = now.date()
        is_overdue = Q(due_date__lt=today) | Q(due_date=today, due_time__lte=now.time())
        deadlines = unfinished.filter(due_date__isnull=False).order_by(
            'due_date', F('due_time').asc(nulls_last=True), 'pk',
        ).values('title', 'due_date', 'due_time')

        completion_pct = round((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0

        evaluate_and_sync_badges(fellow, from_read=True)
        fellow_badges = FellowBadge.objects.filter(fellow=fellow)
        badge_counts = fellow_badges.aggregate(total=Count('pk'), earned=Count('pk', filter=Q(earned=True)))
        earned_badges, total_badges = badge_counts['earned'], badge_counts['total']

        return Response({
            'status': 'success',
            'first_name': first_name,
            'cohort_name': cohort_name,
            'current_phase': current_phase,
            'phases': list(Phase.objects.values('id', 'name', 'description', 'order')),
            'project_name': project_name,
            'project_description': project_description,
            'chapter': chapter_str,
            'team_members': team_members,
            'deadlines': {
                'today': today,
                'overdue': list(deadlines.filter(is_overdue)[:3]),
                'upcoming': list(deadlines.exclude(is_overdue)[:3]),
            },
            'stats': {
                'open_tasks': open_tasks,
                'completed_tasks': completed_tasks,
                'earned_badges': earned_badges,
                'total_badges': total_badges,
                'level_name': badge_rank_title(earned_badges),
                'completion_pct': completion_pct,
            },
            'sdgs': sdgs_data
        })
