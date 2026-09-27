from datetime import date
from smtplib import SMTPException

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseForbidden, HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.urls import path

from .models import (
    Chapter, Cohort, SDG, Fellow, Task, MeetingAvailability, Badge, FellowBadge,
    InviteCode, AvailabilityRequest, availability_task_visibility_filter,
)


@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = ['name', 'country', 'country_code', 'timezone', 'founded_year']
    search_fields = ['name', 'country']


@admin.register(SDG)
class SDGAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'color']
    ordering = ['code']
    search_fields = ['name', 'code']


@admin.register(Cohort)
class CohortAdmin(admin.ModelAdmin):
    list_display = ['name', 'project_name', 'current_phase', 'start_date', 'end_date', 'is_active']
    list_filter = ['is_active', 'current_phase']
    search_fields = ['name', 'project_name', 'project_description']
    filter_horizontal = ['selected_sdgs']


@admin.register(InviteCode)
class InviteCodeAdmin(admin.ModelAdmin):
    list_display = ['code', 'is_active', 'times_used', 'max_uses', 'cohort', 'role', 'expires_at', 'created_at']
    list_filter = ['is_active', 'cohort', 'role']
    search_fields = ['code']
    readonly_fields = ['times_used', 'created_at']
    actions = ['generate_5_codes']

    @admin.action(description="Generate 5 single-use invite codes")
    def generate_5_codes(self, request, queryset):
        active_cohort = Cohort.objects.filter(is_active=True).first()
        created = []
        for _ in range(5):
            code_obj = InviteCode.objects.create(created_by=request.user, cohort=active_cohort)
            created.append(code_obj.code)
        self.message_user(request, f"Successfully generated 5 invite codes: {', '.join(created)}")


class FellowBadgeInline(admin.TabularInline):
    model = FellowBadge
    extra = 0


class TaskInline(admin.TabularInline):
    model = Task
    extra = 0
    fields = ['title', 'scope', 'status', 'source', 'due_date']


class TaskAssignmentForm(forms.Form):
    TARGET_CHOICES = [
        ("fellow", "One fellow"),
        ("cohort_individual", "One cohort — each fellow completes it"),
        ("cohort_team", "One cohort — shared team assignment"),
        ("all_fellows_individual", "All fellows — each gets an individual task"),
        ("all_cohorts_team", "All fellows — one shared task per cohort"),
    ]

    title = forms.CharField(max_length=300)
    description = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}))
    target_mode = forms.ChoiceField(choices=TARGET_CHOICES, initial="all_fellows_individual")
    fellow = forms.ModelChoiceField(queryset=Fellow.objects.none(), required=False)
    cohort = forms.ModelChoiceField(queryset=Cohort.objects.none(), required=False)
    due_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Optional due date.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fellow"].queryset = Fellow.objects.filter(
            role=Fellow.Role.FELLOW,
            user__is_active=True,
        ).select_related("user", "cohort")
        self.fields["cohort"].queryset = Cohort.objects.all()

    def clean(self):
        cleaned = super().clean()
        mode = cleaned.get("target_mode")
        fellow = cleaned.get("fellow")
        cohort = cleaned.get("cohort")
        eligible = Fellow.objects.filter(role=Fellow.Role.FELLOW, user__is_active=True)

        if mode == "fellow" and not fellow:
            self.add_error("fellow", "Choose the fellow who should receive this task.")
        elif mode in {"cohort_individual", "cohort_team"}:
            if not cohort:
                self.add_error("cohort", "Choose a cohort.")
            elif not eligible.filter(cohort=cohort).exists():
                self.add_error("cohort", "This cohort has no active fellows to assign.")
        elif mode == "all_fellows_individual" and not eligible.exists():
            self.add_error("target_mode", "There are no active fellows to assign.")
        elif mode == "all_cohorts_team":
            if not eligible.exists():
                self.add_error("target_mode", "There are no active fellows to assign.")
            elif eligible.filter(cohort__isnull=True).exists():
                self.add_error(
                    "target_mode",
                    "A shared team task needs every active fellow to belong to a cohort. "
                    "Assign the cohortless fellows individually first.",
                )

        if mode == "fellow":
            cleaned["cohort"] = None
        elif mode in {"cohort_individual", "cohort_team"}:
            cleaned["fellow"] = None
        else:
            cleaned["fellow"] = None
            cleaned["cohort"] = None
        return cleaned


def pending_tasks_for_fellow(fellow):
    task_filter = Q(assigned_to=fellow)
    if fellow.cohort_id:
        task_filter |= Q(scope=Task.Scope.TEAM, cohort_id=fellow.cohort_id)
    tasks = list(
        Task.objects.filter(
            task_filter,
            status__in=[Task.Status.PENDING, Task.Status.IN_PROGRESS],
        ).filter(
            availability_task_visibility_filter(fellow)
        ).select_related("availability_request").distinct()
    )
    tasks.sort(key=lambda task: (
        0 if task.source == Task.Source.UNBOUND else 1,
        0 if task.availability_request_id else 1,
        task.due_date or date.max,
        task.created_at,
        task.pk,
    ))
    return tasks


def pending_tasks_email(fellow, tasks):
    full_name = fellow.user.get_full_name().strip()
    first_name = fellow.user.first_name.strip() or (full_name.split()[0] if full_name else "")
    if not first_name:
        first_name = fellow.user.email.partition("@")[0] or fellow.user.username or "there"

    site_base = getattr(settings, "SITE_BASE_URL", "").rstrip("/")
    dashboard_url = f"{site_base}/dashboard/" if site_base else "/dashboard/"
    lines = [
        f"Hi {first_name},",
        "",
        f"You have {len(tasks)} assignment(s) that are not complete yet.",
        "Tasks assigned by UNbound appear first. When2meet requests are first within that group.",
        "",
    ]
    for task in tasks:
        labels = [task.get_source_display()]
        if task.availability_request_id:
            labels.insert(0, "WHEN2MEET")
        labels.append("Team" if task.scope == Task.Scope.TEAM else "Individual")
        due = f" — due {task.due_date.strftime('%b %d, %Y')}" if task.due_date else ""
        lines.append(f"- [{ ' · '.join(labels) }] {task.title}{due}")
        if task.description:
            lines.append(f"  {task.description}")
    lines.extend(["", f"Open your UNbound dashboard: {dashboard_url}"])
    return "\n".join(lines)


@admin.register(Fellow)
class FellowAdmin(admin.ModelAdmin):
    change_list_template = "admin/fellows/fellow/change_list.html"
    list_display = ['__str__', 'role', 'chapter', 'cohort', 'get_current_phase', 'xp_points']
    list_filter = ['role', 'chapter', 'cohort']
    search_fields = ['user__first_name', 'user__last_name', 'user__email']
    inlines = [TaskInline, FellowBadgeInline]

    @admin.display(description='Current Phase')
    def get_current_phase(self, obj):
        return obj.cohort.current_phase if obj.cohort else '-'

    def changelist_view(self, request, extra_context=None):
        context = {
            **(extra_context or {}),
            "can_email_pending_assignments": self.has_change_permission(request),
        }
        return super().changelist_view(request, extra_context=context)

    def get_urls(self):
        custom_urls = [
            path(
                "send-pending-reminders/",
                self.admin_site.admin_view(self.send_pending_reminders),
                name="fellows_fellow_send_pending_reminders",
            ),
        ]
        return custom_urls + super().get_urls()

    def send_pending_reminders(self, request):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        if not self.has_change_permission(request):
            return HttpResponseForbidden("You do not have permission to email fellows.")

        sent = 0
        skipped_no_pending = 0
        skipped_no_email = 0
        failed = 0
        fellows = Fellow.objects.filter(
            role=Fellow.Role.FELLOW,
            user__is_active=True,
        ).select_related("user", "cohort")

        for fellow in fellows:
            tasks = pending_tasks_for_fellow(fellow)
            if not tasks:
                skipped_no_pending += 1
                continue
            email = (fellow.user.email or "").strip()
            if not email:
                skipped_no_email += 1
                continue
            try:
                delivered = send_mail(
                    subject="Your pending UNbound assignments",
                    message=pending_tasks_email(fellow, tasks),
                    from_email=None,
                    recipient_list=[email],
                    fail_silently=False,
                )
                if delivered:
                    sent += 1
                else:
                    failed += 1
            except (SMTPException, OSError, TimeoutError):
                failed += 1

        if sent:
            self.message_user(
                request,
                f"Sent pending assignment emails to {sent} fellow(s).",
                level=messages.SUCCESS,
            )
        if skipped_no_pending or skipped_no_email:
            details = []
            if skipped_no_pending:
                details.append(f"{skipped_no_pending} had no incomplete assignments")
            if skipped_no_email:
                details.append(f"{skipped_no_email} had no email address")
            self.message_user(request, "Skipped " + " and ".join(details) + ".", level=messages.INFO)
        if failed:
            self.message_user(
                request,
                f"Email could not be sent to {failed} fellow(s). Check the configured email backend.",
                level=messages.ERROR,
            )
        return redirect("admin:fellows_fellow_changelist")


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    change_list_template = "admin/fellows/task/change_list.html"
    list_display = ['title', 'assigned_to', 'scope', 'status', 'source', 'due_date', 'created_at']
    list_filter = ['status', 'scope', 'source']
    search_fields = ['title', 'description']
    list_editable = ['status']

    def get_urls(self):
        custom_urls = [
            path(
                "assign/",
                self.admin_site.admin_view(self.assign_task_view),
                name="fellows_task_assign",
            ),
        ]
        return custom_urls + super().get_urls()

    def assign_task_view(self, request):
        if not self.has_add_permission(request):
            return HttpResponseForbidden("You do not have permission to assign tasks.")

        form = TaskAssignmentForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            data = form.cleaned_data
            mode = data["target_mode"]
            scope = Task.Scope.TEAM if mode.endswith("_team") else Task.Scope.PERSONAL
            with transaction.atomic():
                created = Task.assign_task(
                    title=data["title"],
                    description=data["description"],
                    scope=scope,
                    due_date=data["due_date"],
                    target_mode=mode,
                    fellow=data["fellow"],
                    cohort=data["cohort"],
                    source=Task.Source.UNBOUND,
                )
            if created:
                self.message_user(
                    request,
                    f"Created {len(created)} UNbound task record(s).",
                    level=messages.SUCCESS,
                )
                return redirect("admin:fellows_task_changelist")
            form.add_error(None, "No tasks were created for this target.")

        context = {
            **self.admin_site.each_context(request),
            "title": "Assign a task",
            "opts": self.model._meta,
            "form": form,
        }
        return render(request, "admin/fellows/task/assignment_form.html", context)


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ['name', 'trigger_type', 'required_task_count', 'required_phase', 'xp_reward', 'color', 'order']
    ordering = ['order']


@admin.register(AvailabilityRequest)
class AvailabilityRequestAdmin(admin.ModelAdmin):
    list_display = ['title', 'cohort', 'assign_to_all', 'start_date', 'end_date', 'deadline', 'is_active', 'get_response_summary', 'created_at']
    list_filter = ['is_active', 'assign_to_all', 'cohort']
    search_fields = ['title', 'description']
    readonly_fields = ['created_at', 'get_response_details']
    fieldsets = (
        ('Request Details', {
            'fields': ('title', 'description', 'is_active')
        }),
        ('Date & Time Window', {
            'fields': (('start_date', 'end_date'), ('start_hour', 'end_hour'), 'deadline')
        }),
        ('Assignment Target', {
            'fields': ('cohort', 'assign_to_all'),
            'description': 'Choose a specific Cohort or check "Assign to all" to send to all fellows.'
        }),
        ('Response Tracking', {
            'fields': ('get_response_details', 'created_at')
        }),
    )
    actions = ['sync_tasks']

    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
        if obj.is_active:
            obj.create_tasks_for_fellows()

    @admin.action(description="Ensure UNbound tasks exist for all assigned fellows")
    def sync_tasks(self, request, queryset):
        synced_requests = 0
        skipped_inactive = 0
        for req_obj in queryset:
            if req_obj.is_active:
                req_obj.create_tasks_for_fellows()
                synced_requests += 1
            else:
                skipped_inactive += 1

        message = f"UNbound tasks synced for {synced_requests} active request(s)."
        if skipped_inactive:
            message += f" Skipped {skipped_inactive} inactive request(s)."
        self.message_user(request, message)

    @admin.display(description="Responses")
    def get_response_summary(self, obj):
        target_fellows = obj.target_fellows()
        total_fellows = target_fellows.count()
        responded = target_fellows.filter(
            availability_slots__availability_request=obj,
            availability_slots__is_available=True,
        ).distinct().count()
        return f"{responded}/{total_fellows} responded"

    @admin.display(description="Fellow Response Breakdown")
    def get_response_details(self, obj):
        if not obj.pk:
            return "Save request first to track responses."
        target_fellows = obj.target_fellows()

        responded_ids = set(MeetingAvailability.objects.filter(
            availability_request=obj,
            is_available=True
        ).values_list('fellow_id', flat=True))

        responded_names = [f.user.get_full_name() or f.user.email for f in target_fellows if f.id in responded_ids]
        pending_names = [f.user.get_full_name() or f.user.email for f in target_fellows if f.id not in responded_ids]

        summary = f"Total Target Fellows: {target_fellows.count()}\n"
        summary += f"✓ Responded ({len(responded_names)}):\n  " + (", ".join(responded_names) if responded_names else "None yet") + "\n\n"
        summary += f"⏳ Pending ({len(pending_names)}):\n  " + (", ".join(pending_names) if pending_names else "None! All responded")
        return summary


@admin.register(MeetingAvailability)
class MeetingAvailabilityAdmin(admin.ModelAdmin):
    list_display = ['fellow', 'availability_request', 'date', 'day_of_week', 'hour', 'is_available']
    list_filter = ['is_available', 'availability_request', 'date', 'day_of_week']