from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render, redirect
from allauth.socialaccount.models import SocialAccount
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .google_api import (
    GoogleConnectionError,
    GoogleIntegrationError,
    create_google_task,
    delete_google_task,
    fetch_calendar_events,
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
from .models import MeetingAvailability, Task, Fellow, FellowBadge, InviteCode, SDG, Cohort
from .serializers import MeetingAvailabilitySerializer, TaskSerializer
from .badges_engine import evaluate_and_sync_badges


def ensure_default_sdgs_exist():
    """Seeds all 17 official UN Sustainable Development Goals with official names and colors."""
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
    for item in UN_SDGS:
        SDG.objects.get_or_create(code=item['code'], defaults=item)


def google_account_details(user):
    account = SocialAccount.objects.filter(user=user, provider='google').first()
    data = account.extra_data if account else {}
    name = data.get('name') or user.get_full_name() or user.email or user.username
    return {
        'connected': has_google_connection(user),
        'name': name,
        'email': data.get('email') or user.email,
        'picture': data.get('picture', ''),
    }


@login_required(login_url='account_login')
def dashboard_view(request):
    """Render the dashboard shell; each Google mini-app loads live data via API."""
    return render(request, 'fellow-dashboard.html', {
        'google_account': google_account_details(request.user),
    })


def register_code_view(request):
    """View where new fellows enter their invitation code before logging in with Google."""
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
                    return redirect('/accounts/google/login/')
                else:
                    error = msg
            except InviteCode.DoesNotExist:
                error = "Invalid invitation code. Please reach out to the Fellowship Execs for access."

    return render(request, 'account/register_code.html', {'error': error})


class GoogleConnectionAPIView(APIView):
    """Shared connection handling for all Google-backed endpoints."""

    def connection_response(self, user):
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


class GoogleAccountView(APIView):
    def get(self, request, *args, **kwargs):
        return Response(google_account_details(request.user))


class GoogleCalendarEventsView(GoogleConnectionAPIView):
    def get(self, request, *args, **kwargs):
        disconnected = self.connection_response(request.user)
        if disconnected:
            return disconnected
        try:
            return Response({'connected': True, 'events': fetch_calendar_events(request.user)})
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
            files = fetch_drive_folder_contents(request.user, folder_id=folder_id)
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
        ensure_default_sdgs_exist()

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

        ensure_default_sdgs_exist()

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


class BadgesAPIView(APIView):
    def get(self, request, *args, **kwargs):
        if not hasattr(request.user, 'fellow_profile'):
            return Response({'status': 'error', 'detail': 'Fellow profile missing.'}, status=status.HTTP_400_BAD_REQUEST)

        fellow = request.user.fellow_profile
        evaluate_and_sync_badges(fellow)

        fellow_badges = FellowBadge.objects.filter(fellow=fellow).select_related('badge').order_by('badge__order')
        earned_count = fellow_badges.filter(earned=True).count()
        total_count = fellow_badges.count()

        if earned_count >= 9:
            level_title = "UNbound Legend • Level 4"
        elif earned_count >= 7:
            level_title = "Visionary • Level 3"
        elif earned_count >= 4:
            level_title = "Trailblazer • Level 2"
        elif earned_count >= 1:
            level_title = "Explorer • Level 1"
        else:
            level_title = "Pioneer • Level 1"

        badges_data = []
        for fb in fellow_badges:
            b = fb.badge
            badges_data.append({
                'id': b.id,
                'name': b.name,
                'description': b.description,
                'color': b.color,
                'icon_class': b.icon_class,
                'earned': fb.earned,
                'progress': fb.progress,
                'earned_at': fb.earned_at,
            })

        return Response({
            'status': 'success',
            'level_title': level_title,
            'earned_count': earned_count,
            'total_count': total_count,
            'xp_points': fellow.xp_points,
            'badges': badges_data
        })


def seed_initial_prototype_tasks(fellow):
    """Seed prototype tasks matching the design spec if fellow has no tasks."""
    if Task.objects.filter(assigned_to=fellow).exists():
        return

    prototype_deliverables = [
        {
            'title': 'Submit Community Needs Assessment',
            'description': 'Upload your completed empathy-interview synthesis to the cohort folder.',
            'scope': Task.Scope.TEAM,
            'source': Task.Source.UNBOUND,
            'status': Task.Status.PENDING,
            'icon': 'fa-pen-to-square',
            'color': '#00B4D8'
        },
        {
            'title': 'Prototype Pitch Deck (v1)',
            'description': 'Draft the 6-slide prototype pitch using the UNbound template.',
            'scope': Task.Scope.TEAM,
            'source': Task.Source.UNBOUND,
            'status': Task.Status.PENDING,
            'icon': 'fa-desktop',
            'color': '#7c5cff'
        },
        {
            'title': 'Complete Design-Thinking Module 3',
            'description': 'Watch the Ideation lesson and submit your reflection.',
            'scope': Task.Scope.PERSONAL,
            'source': Task.Source.UNBOUND,
            'status': Task.Status.PENDING,
            'icon': 'fa-graduation-cap',
            'color': '#e0a009'
        },
        {
            'title': 'Map Your SDG Targets',
            'description': 'Select the specific UN targets your project will measure against.',
            'scope': Task.Scope.PERSONAL,
            'source': Task.Source.UNBOUND,
            'status': Task.Status.PENDING,
            'icon': 'fa-wave-square',
            'color': '#e82e2e'
        }
    ]

    for item in prototype_deliverables:
        Task.objects.create(
            assigned_to=fellow,
            cohort=fellow.cohort,
            **item
        )


class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer

    def get_queryset(self):
        if not hasattr(self.request.user, 'fellow_profile'):
            return Task.objects.none()
        fellow = self.request.user.fellow_profile
        seed_initial_prototype_tasks(fellow)

        if fellow.cohort:
            qs = Task.objects.filter(
                Q(assigned_to=fellow) |
                (Q(scope=Task.Scope.TEAM) & Q(cohort=fellow.cohort))
            )
        else:
            qs = Task.objects.filter(assigned_to=fellow)

        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        fellow = self.request.user.fellow_profile
        scope = serializer.validated_data.get('scope', Task.Scope.PERSONAL)
        icon = serializer.validated_data.get('icon') or ('fa-pen-to-square' if scope == Task.Scope.TEAM else 'fa-check')
        color = serializer.validated_data.get('color') or ('#00B4D8' if scope == Task.Scope.TEAM else '#e0a009')

        task = serializer.save(
            assigned_to=fellow,
            cohort=fellow.cohort,
            source=Task.Source.SELF,
            icon=icon,
            color=color,
        )
        if has_google_connection(self.request.user):
            sync_task_to_google(self.request.user, task)
        evaluate_and_sync_badges(fellow)

    def perform_update(self, serializer):
        task = serializer.save()
        if has_google_connection(self.request.user):
            sync_task_to_google(self.request.user, task)
        evaluate_and_sync_badges(task.assigned_to)

    def perform_destroy(self, instance):
        google_task_id = instance.google_task_id
        fellow = instance.assigned_to
        instance.delete()
        if google_task_id and has_google_connection(self.request.user):
            delete_task_from_google(self.request.user, google_task_id)
        evaluate_and_sync_badges(fellow)


class MeetingAvailabilityViewSet(viewsets.ModelViewSet):
    serializer_class = MeetingAvailabilitySerializer

    def get_queryset(self):
        if not hasattr(self.request.user, 'fellow_profile'):
            return MeetingAvailability.objects.none()
        fellow = self.request.user.fellow_profile
        return MeetingAvailability.objects.filter(fellow=fellow)

    def perform_create(self, serializer):
        serializer.save(fellow=self.request.user.fellow_profile)
        evaluate_and_sync_badges(self.request.user.fellow_profile)

    @action(detail=False, methods=['post'], url_path='bulk-save')
    def bulk_save(self, request):
        if not hasattr(request.user, 'fellow_profile'):
            return Response({'detail': 'Fellow profile missing.'}, status=status.HTTP_400_BAD_REQUEST)

        fellow = request.user.fellow_profile
        slots = request.data.get('slots', [])

        updated_records = []
        for s in slots:
            day = s.get('day_of_week')
            hour = s.get('hour')
            is_avail = bool(s.get('is_available', False))

            if day is not None and hour is not None:
                obj, _ = MeetingAvailability.objects.update_or_create(
                    fellow=fellow,
                    day_of_week=day,
                    hour=hour,
                    defaults={'is_available': is_avail}
                )
                updated_records.append(obj)

        evaluate_and_sync_badges(fellow)
        serializer = self.get_serializer(updated_records, many=True)
        return Response({'status': 'success', 'slots': serializer.data})

    @action(detail=False, methods=['post'], url_path='sync-google')
    def sync_google(self, request):
        if not has_google_connection(request.user):
            return Response({
                'connected': False,
                'detail': 'Connect your Google account to sync calendar availability.'
            }, status=status.HTTP_403_FORBIDDEN)

        tz_str = request.data.get('timezone', 'America/Monterrey')
        try:
            slots = sync_user_calendar_availability(request.user, tz_str=tz_str)
            if hasattr(request.user, 'fellow_profile'):
                evaluate_and_sync_badges(request.user.fellow_profile)
            return Response({'connected': True, 'status': 'success', 'slots': slots})
        except GoogleIntegrationError as exc:
            return Response({'connected': True, 'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

    @action(detail=False, methods=['get'], url_path='group-availability')
    def group_availability(self, request):
        if not hasattr(request.user, 'fellow_profile'):
            return Response({'detail': 'Fellow profile missing.'}, status=status.HTTP_400_BAD_REQUEST)

        fellow = request.user.fellow_profile

        if fellow.cohort:
            cohort_fellows = Fellow.objects.filter(cohort=fellow.cohort).select_related('user')
        elif fellow.chapter:
            cohort_fellows = Fellow.objects.filter(chapter=fellow.chapter).select_related('user')
        else:
            cohort_fellows = Fellow.objects.select_related('user').all()

        total_members = cohort_fellows.count()
        if total_members == 0:
            total_members = 1

        avail_qs = MeetingAvailability.objects.filter(
            fellow__in=cohort_fellows,
            is_available=True
        ).select_related('fellow__user')

        matrix_data = {(d, h): [] for d in range(7) for h in range(9, 18)}
        for record in avail_qs:
            key = (record.day_of_week, record.hour)
            if key in matrix_data:
                name = record.fellow.user.get_full_name() or record.fellow.user.username
                matrix_data[key].append(name)

        tz_str = request.query_params.get('timezone', 'America/Monterrey')
        shared_email = getattr(settings, 'GOOGLE_SHARED_WORKSPACE_EMAIL', 'primary')
        shared_events_grid = {}

        if has_google_connection(request.user):
            try:
                tz = ZoneInfo(tz_str)
            except Exception:
                tz = ZoneInfo('America/Monterrey')
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
            'total_members': total_members,
            'matrix': formatted_matrix
        })


class DashboardOverviewAPIView(APIView):
    def get(self, request, *args, **kwargs):
        if not hasattr(request.user, 'fellow_profile'):
            return Response({'status': 'error', 'detail': 'Fellow profile missing.'}, status=status.HTTP_400_BAD_REQUEST)

        fellow = request.user.fellow_profile
        user = request.user

        first_name = user.first_name or (user.get_full_name().split()[0] if user.get_full_name() else user.email.split('@')[0])

        cohort = fellow.cohort
        cohort_name = f"Cohort {cohort.name}" if cohort else "Cohort 2026–2027"
        current_phase = cohort.current_phase if (cohort and cohort.current_phase) else "Launch Sequence"
        project_name = cohort.project_name if (cohort and cohort.project_name) else "Bridges to Brighter Smiles"
        project_description = cohort.project_description if cohort else ""

        if fellow.chapter:
            chapter_str = f"{fellow.chapter.name}, {fellow.chapter.country_code}"
        else:
            chapter_str = "Monterrey, MX"

        team_members = []
        if cohort:
            cohort_fellows = Fellow.objects.filter(cohort=cohort).select_related('user')
        else:
            cohort_fellows = Fellow.objects.select_related('user').all()[:6]

        for cf in cohort_fellows:
            sa = SocialAccount.objects.filter(user=cf.user, provider='google').first()
            picture = sa.extra_data.get('picture', '') if sa else ''
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

        ensure_default_sdgs_exist()
        sdgs_data = []
        if cohort and cohort.selected_sdgs.exists():
            for sdg in cohort.selected_sdgs.all().order_by('code'):
                sdgs_data.append({
                    'code': sdg.code,
                    'name': sdg.name,
                    'color': sdg.color
                })
        else:
            default_sdgs = SDG.objects.filter(code__in=[3, 4, 10])
            if cohort:
                cohort.selected_sdgs.set(default_sdgs)
            for sdg in default_sdgs.order_by('code'):
                sdgs_data.append({
                    'code': sdg.code,
                    'name': sdg.name,
                    'color': sdg.color
                })

        seed_initial_prototype_tasks(fellow)
        if cohort:
            tasks_qs = Task.objects.filter(
                Q(assigned_to=fellow) | (Q(scope=Task.Scope.TEAM) & Q(cohort=cohort))
            )
        else:
            tasks_qs = Task.objects.filter(assigned_to=fellow)

        open_tasks = tasks_qs.exclude(status=Task.Status.COMPLETE).count()
        completed_tasks = tasks_qs.filter(status=Task.Status.COMPLETE).count()
        total_tasks = tasks_qs.count()

        completion_pct = round((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 42

        evaluate_and_sync_badges(fellow)
        fellow_badges = FellowBadge.objects.filter(fellow=fellow)
        earned_badges = fellow_badges.filter(earned=True).count()
        total_badges = fellow_badges.count() or 9

        if earned_badges >= 9:
            level_name = "UNbound Legend"
        elif earned_badges >= 7:
            level_name = "Visionary level"
        elif earned_badges >= 4:
            level_name = "Trailblazer level"
        else:
            level_name = "Pioneer level"

        return Response({
            'status': 'success',
            'first_name': first_name,
            'cohort_name': cohort_name,
            'current_phase': current_phase,
            'project_name': project_name,
            'project_description': project_description,
            'chapter': chapter_str,
            'team_members': team_members,
            'stats': {
                'open_tasks': open_tasks,
                'completed_tasks': completed_tasks,
                'earned_badges': earned_badges,
                'total_badges': total_badges,
                'level_name': level_name,
                'completion_pct': completion_pct,
            },
            'sdgs': sdgs_data
        })