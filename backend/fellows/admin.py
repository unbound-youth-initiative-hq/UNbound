from base64 import b64encode
from uuid import UUID


from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin.options import IncorrectLookupParameters
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponseForbidden, HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import path
from django.utils import timezone
from django.utils.html import format_html

from .badges_engine import evaluate_and_sync_badges
from .forms import AvailabilityRequestAdminForm, BadgeAdminForm, InviteBatchForm, SharedDriveResourceForm
from .models import (
    Chapter, Cohort, CohortDriveLink, ConfirmedMeeting, SharedDriveResource, SDG, Fellow, Task, MeetingAvailability, Badge, FellowBadge,
    InviteCode, AvailabilityRequest, Phase, ReminderBatch, ReminderDelivery,
)
from .resource_appearance import RESOURCE_PREVIEW_OPTIONS


from .reminder_content import (
    incomplete_reminder_tasks, pending_tasks_email, pending_tasks_for_fellow, task_reminder_drafts,
)


admin.site.site_header = 'UNbound Administration'
admin.site.site_title = 'UNbound'
admin.site.index_title = 'Manage your fellowship'


@admin.register(Phase)
class PhaseAdmin(admin.ModelAdmin):
    list_display = ['name', 'description', 'order']
    list_editable = ['order']
    search_fields = ['name']


@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = ['name', 'country', 'country_code', 'timezone', 'founded_year']
    search_fields = ['name', 'country']


@admin.register(SDG)
class SDGAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'color']
    ordering = ['code']
    search_fields = ['name', 'code']


class ResourceAppearanceAdmin:
    class Media:
        css = {'all': (
            'https://fonts.googleapis.com/css2?family=Montserrat:wght@400..800&display=swap',
            'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css',
            'resource-cards.css',
        )}
        js = ('resource-preview.js',)

    @admin.display(description='Fellow dashboard preview')
    def resource_preview(self, resource):
        return render_to_string('admin/fellows/resource_preview.html', {
            'link': resource, 'options': RESOURCE_PREVIEW_OPTIONS,
        })


class CohortDriveLinkInline(ResourceAppearanceAdmin, admin.StackedInline):
    model = CohortDriveLink
    fields = [
        'title', 'url', 'description', ('resource_type_override', 'resource_icon_override'),
        'resource_preview', ('is_published', 'pinned_by'),
    ]
    readonly_fields = ['resource_preview', 'pinned_by']
    extra = 0

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('pinned_by__user')


@admin.register(Cohort)
class CohortAdmin(admin.ModelAdmin):
    inlines = [CohortDriveLinkInline]
    list_display = ['name', 'project_name', 'phase', 'start_date', 'end_date', 'is_active']
    list_select_related = ['phase']
    fieldsets = [('Cohort', {'fields': ('name', 'is_active', ('start_date', 'end_date'))}), ('Project and progress', {'fields': ('project_name', 'project_description', 'phase', 'selected_sdgs')})]
    list_filter = ['is_active', 'phase']
    search_fields = ['name', 'project_name', 'project_description']
    filter_horizontal = ['selected_sdgs']

    def get_deleted_objects(self, objs, request):
        deleted, counts, permissions, protected = super().get_deleted_objects(objs, request)
        polls = AvailabilityRequest.objects.filter(cohort__in=objs, assign_to_all=False)
        if polls.exists():
            protected = [*protected, 'Reassign the targeted WhenBound polls before deleting their cohort. You can mark the cohort inactive to archive it.']
        return deleted, counts, permissions, protected


@admin.register(SharedDriveResource)
class SharedDriveResourceAdmin(ResourceAppearanceAdmin, admin.ModelAdmin):
    form = SharedDriveResourceForm
    readonly_fields = ['resource_preview']
    list_display = ['title', 'audience', 'is_published']
    list_filter = ['audience', 'is_published', 'cohorts']
    filter_horizontal = ['cohorts']
    search_fields = ['title', 'description', 'url']
    fieldsets = [
        ('Resource', {'fields': ('title', 'url', 'description')}),
        ('Appearance', {'fields': (('resource_type_override', 'resource_icon_override'), 'resource_preview')}),
        ('Audience and publication', {'fields': ('audience', 'cohorts', 'is_published')}),
    ]


@admin.register(ConfirmedMeeting)
class ConfirmedMeetingAdmin(admin.ModelAdmin):
    list_display = ['title', 'cohort', 'starts_at', 'ends_at', 'is_published']
    list_filter = ['cohort', 'is_published']
    list_select_related = ['cohort']
    search_fields = ['title']


@admin.register(InviteCode)
class InviteCodeAdmin(admin.ModelAdmin):
    list_display = ['code', 'is_active', 'times_used', 'max_uses', 'cohort', 'role', 'expires_at', 'created_at']
    list_filter = ['is_active', 'cohort', 'role']
    search_fields = ['code']
    readonly_fields = ['times_used', 'created_at']

    def get_urls(self):
        return [
            path('generate/', self.admin_site.admin_view(self.generate_invites), name='fellows_invitecode_generate'),
        ] + super().get_urls()

    def generate_invites(self, request):
        if not self.has_add_permission(request):
            return HttpResponseForbidden('You do not have permission to generate invitations.')
        form = InviteBatchForm(request.POST if request.method == 'POST' else None)
        if request.method == 'POST' and form.is_valid():
            with transaction.atomic():
                created = [
                    InviteCode.objects.create(
                        created_by=request.user, cohort=form.cleaned_data['cohort'], max_uses=1,
                    )
                    for _ in range(5)
                ]
            self.message_user(request, f"Created five single-use invitations: {', '.join(invite.code for invite in created)}")
            return redirect('admin:fellows_invitecode_changelist')
        return render(request, 'admin/fellows/invitecode/generate.html', {
            **self.admin_site.each_context(request), 'title': 'Generate invitations', 'form': form,
        })


class FellowBadgeInline(admin.TabularInline):
    model = FellowBadge
    extra = 0


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
    target_mode = forms.ChoiceField(label='Assign to', choices=[('', 'Choose a target'), *TARGET_CHOICES])
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


@admin.register(Fellow)
class FellowAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'role', 'chapter', 'cohort', 'get_current_phase', 'xp_points']
    list_filter = ['role', 'chapter', 'cohort']
    search_fields = ['user__first_name', 'user__last_name', 'user__email']
    inlines = [FellowBadgeInline]
    autocomplete_fields = ['user', 'chapter', 'cohort']
    list_select_related = ['user', 'chapter', 'cohort__phase']
    readonly_fields = ['xp_points', 'get_current_phase']
    fieldsets = [
        ('Fellow', {'fields': ('user', 'role', 'chapter', 'cohort')}),
        ('Progress', {'fields': ('get_current_phase', 'xp_points')}),
        ('Preferences', {'fields': ('accent_palette', 'meeting_timezone'), 'classes': ('collapse',)}),
    ]

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.method == 'POST' and getattr(request.resolver_match, 'url_name', '') == 'fellows_fellow_change':
            return queryset.select_for_update(of=('self',))
        return queryset

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        if formset.model is FellowBadge and formset.has_changed():
            evaluate_and_sync_badges(form.instance)

    def has_prepare_drafts_permission(self, request):
        return self.has_change_permission(request) and (
            request.user.has_perm('fellows.view_task') or request.user.has_perm('fellows.change_task')
        )

    @admin.display(description='Current Phase')
    def get_current_phase(self, obj):
        return obj.cohort.current_phase if obj.cohort else '-'

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
        if not self.has_prepare_drafts_permission(request):
            return HttpResponseForbidden('You do not have permission to email fellows.')
        if request.method not in ('GET', 'POST'):
            return HttpResponseNotAllowed(['GET', 'POST'])
        if request.method == 'POST':
            try:
                batch_id = UUID(request.POST.get('batch_id', ''))
            except (ValueError, TypeError, AttributeError):
                return HttpResponseForbidden('Invalid reminder preview.')
            with transaction.atomic():
                batch = ReminderBatch.objects.select_for_update().filter(pk=batch_id, created_by=request.user).first()
                if not batch:
                    self.message_user(request, 'Reminder preview not found. Open a new preview.', messages.ERROR)
                    return redirect('admin:fellows_fellow_changelist')
                if batch.queued_at:
                    self.message_user(request, 'This batch was already submitted; no duplicate emails were queued.', messages.INFO)
                    return redirect('admin:fellows_fellow_changelist')
                batch.queued_at = timezone.now()
                batch.save(update_fields=['queued_at'])
                batch.deliveries.filter(state='draft').update(state='queued')
            if settings.EMAIL_BACKEND.endswith('console.EmailBackend'):
                from .reminders import dispatch_reminders
                dispatch_reminders(batch.deliveries.all())
                self.message_user(request, 'Reminder previews were written to server logs. No inbox delivery was attempted.', messages.SUCCESS)
            else:
                self.message_user(request, 'Reminders queued. The delivery worker will process this batch.', messages.SUCCESS)
            return redirect('admin:fellows_fellow_changelist')
        batch = ReminderBatch.objects.create(created_by=request.user)
        rows = []
        for fellow in Fellow.objects.filter(role=Fellow.Role.FELLOW, user__is_active=True).select_related('user', 'cohort'):
            tasks = pending_tasks_for_fellow(fellow)
            if tasks and fellow.user.email:
                rows.append(ReminderDelivery(batch=batch, fellow=fellow, email=fellow.user.email, body=pending_tasks_email(fellow, tasks)))
        ReminderDelivery.objects.bulk_create(rows)
        return render(request, 'admin/fellows/fellow/reminder_preview.html', {
            **self.admin_site.each_context(request), 'opts': self.model._meta,
            'title': 'Review pending-assignment reminders', 'batch': batch,
            'deliveries': rows, 'console_mode': settings.EMAIL_BACKEND.endswith('console.EmailBackend'),
        })


class TaskEditForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = '__all__'

    def clean(self):
        values = super().clean()
        if values.get('scope') == Task.Scope.TEAM and not values.get('cohort'):
            self.add_error('cohort', 'Choose the cohort that shares this task.')
        if values.get('scope') == Task.Scope.PERSONAL and not values.get('assigned_to'):
            self.add_error('assigned_to', 'Choose the fellow responsible for this task.')
        return values


class OverdueTaskFilter(admin.SimpleListFilter):
    title = 'Deadline'
    parameter_name = 'deadline'

    def lookups(self, request, model_admin):
        return [('overdue', 'Overdue and incomplete')]

    def queryset(self, request, queryset):
        if self.value() == 'overdue':
            return overdue_tasks(queryset)
        return queryset


def overdue_tasks(queryset, *, now=None):
    now = now or timezone.localtime()
    return incomplete_reminder_tasks(queryset).filter(
        Q(due_date__lt=now.date()) | Q(due_date=now.date(), due_time__lte=now.time()),
    )


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    form = TaskEditForm
    change_list_template = "admin/fellows/task/change_list.html"
    actions = ['prepare_selected_task_drafts']
    list_display = ['title', 'assigned_to', 'scope', 'status', 'source', 'due_date', 'due_time', 'created_at']
    list_filter = [OverdueTaskFilter, 'status', 'scope', 'source', 'cohort']
    search_fields = ['title', 'description', 'assigned_to__user__email', 'assigned_to__user__first_name', 'assigned_to__user__last_name']
    list_select_related = ['assigned_to__user', 'cohort']
    fieldsets = [('Assignment', {'fields': ('title', 'description', 'source', 'status', ('due_date', 'due_time'))}), ('Who completes it', {'fields': ('scope', 'assigned_to', 'cohort')}), ('Appearance', {'fields': ('icon', 'color'), 'classes': ('collapse',)})]
    autocomplete_fields = ['assigned_to', 'cohort']

    def has_task_drafts_permission(self, request):
        return self.has_view_or_change_permission(request) and request.user.has_perm('fellows.change_fellow')

    def changelist_view(self, request, extra_context=None):
        can_prepare_drafts = self.has_task_drafts_permission(request)
        if request.method == 'POST' and 'prepare_overdue_task_drafts' in request.POST:
            if not can_prepare_drafts:
                raise PermissionDenied
            try:
                tasks = self.get_changelist_instance(request).queryset
            except IncorrectLookupParameters:
                return super().changelist_view(request, extra_context)
            now = timezone.localtime()
            return self.render_task_drafts(request, overdue_tasks(tasks, now=now), now=now, overdue=True)
        return super().changelist_view(request, {
            **(extra_context or {}), 'can_prepare_task_drafts': can_prepare_drafts,
        })

    @admin.action(permissions=['task_drafts'], description='Email about selected tasks')
    def prepare_selected_task_drafts(self, request, queryset):
        return self.render_task_drafts(request, incomplete_reminder_tasks(queryset), now=timezone.localtime())

    def render_task_drafts(self, request, queryset, *, now, overdue=False):
        drafts, skipped = task_reminder_drafts(queryset, now=now)
        return render(request, 'admin/fellows/task/email_drafts.html', {
            **self.admin_site.each_context(request),
            'title': 'Overdue task email drafts' if overdue else 'Selected task email drafts',
            'drafts': drafts, 'skipped': skipped, 'overdue': overdue,
            'back_url': request.get_full_path(),
        })

    def add_view(self, request, form_url='', extra_context=None):
        return redirect('admin:fellows_task_assign')


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

        form = TaskAssignmentForm(request.POST if request.method == 'POST' else None)
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

        recipient_count_by_cohort = dict(
            Fellow.objects.filter(role=Fellow.Role.FELLOW, user__is_active=True).order_by()
            .values_list('cohort_id').annotate(total=Count('pk'))
        )
        context = {
            **self.admin_site.each_context(request),
            "title": "Assign a task",
            "opts": self.model._meta,
            "form": form,
            "recipient_counts": {
                "cohorts": recipient_count_by_cohort,
                "total": sum(recipient_count_by_cohort.values()),
                "unassigned": recipient_count_by_cohort.get(None, 0),
            },
        }
        return render(request, "admin/fellows/task/assignment_form.html", context)


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    form = BadgeAdminForm
    readonly_fields = ['current_artwork']

    class Media:
        css = {'all': ('badge-art.css',)}

    @admin.display(description='Current artwork')
    def current_artwork(self, badge):
        if not badge:
            return 'Choose artwork or upload an image.'
        if badge.icon_png:
            return format_html('<img width="48" alt="Uploaded badge icon" src="data:image/png;base64,{}">',
                               b64encode(badge.icon_png).decode('ascii'))
        if badge.artwork:
            return format_html('<span class="admin-badge-preview"><span class="badge-art badge-art-{}" '
                               'aria-hidden="true"></span></span> {}', badge.artwork, badge.get_artwork_display())
        return badge.icon_class

    prepopulated_fields = {'slug': ('name',)}
    list_display = ['name', 'trigger_type', 'required_task_count', 'required_phase', 'xp_reward', 'color', 'order']
    ordering = ['order']
    fieldsets = [('Badge', {'fields': ('name', 'slug', 'description', 'current_artwork', 'artwork', 'custom_icon', 'remove_custom_icon', 'icon_class', 'color', 'order')}), ('How it is earned', {'fields': ('trigger_type', 'required_task_count', 'required_phase', 'xp_reward')})]

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == 'required_phase':
            return forms.ChoiceField(required=False, choices=[('', 'No phase requirement')] + [(p.name, p.name) for p in Phase.objects.all()])
        return super().formfield_for_dbfield(db_field, request, **kwargs)


@admin.register(AvailabilityRequest)
class AvailabilityRequestAdmin(admin.ModelAdmin):
    form = AvailabilityRequestAdminForm
    list_display = ['title', 'cohort', 'assign_to_all', 'start_date', 'end_date', 'deadline', 'is_active', 'get_response_summary', 'created_at']
    list_filter = ['is_active', 'assign_to_all', 'cohort']
    search_fields = ['title', 'description']
    readonly_fields = ['created_at', 'get_response_details']
    fieldsets = (
        ('Request Details', {
            'fields': ('title', 'description', 'is_active')
        }),
        ('Possible meeting times', {
            'fields': (('start_date', 'end_date'), ('start_hour', 'end_hour'), 'reset_snapshot', 'confirm_response_reset'),
            'description': 'Both dates are included. Enter hours in Monterrey time. The end hour is exclusive. Use 24 for midnight. Fellows see slots in their selected time zone.',
        }),
        ('Response due date', {
            'fields': ('deadline',),
            'description': 'This date appears on the fellow’s WhenBound task. An active poll can still accept late responses.',
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

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        # Django's change form wraps this POST in a transaction. Hold the same
        # lock used by the response service across validation and saving.
        if request.method == 'POST' and getattr(request.resolver_match, 'url_name', '') == 'fellows_availabilityrequest_change':
            return queryset.select_for_update()
        return queryset

    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.action(permissions=['change'], description="Repair linked tasks for selected polls")
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
            availability_submissions__availability_request=obj,
        ).distinct().count()
        return f"{responded}/{total_fellows} responded"

    @admin.display(description="Fellow Response Breakdown")
    def get_response_details(self, obj):
        if not obj.pk:
            return "Save request first to track responses."
        target_fellows = obj.target_fellows()

        responded_ids = set(obj.submissions.values_list('fellow_id', flat=True))

        responded_names = [f.user.get_full_name() or f.user.email for f in target_fellows if f.id in responded_ids]
        pending_names = [f.user.get_full_name() or f.user.email for f in target_fellows if f.id not in responded_ids]

        summary = f"Total Target Fellows: {target_fellows.count()}\n"
        summary += f"✓ Responded ({len(responded_names)}):\n  " + (", ".join(responded_names) if responded_names else "None yet") + "\n\n"
        summary += f"⏳ Pending ({len(pending_names)}):\n  " + (", ".join(pending_names) if pending_names else "None! All responded")
        return summary


@admin.register(MeetingAvailability)
class MeetingAvailabilityAdmin(admin.ModelAdmin):
    def has_module_permission(self, request):
        return request.user.is_superuser

    list_display = ['fellow', 'availability_request', 'date', 'day_of_week', 'hour', 'is_available']
    list_filter = ['is_available', 'availability_request', 'date', 'day_of_week']

@admin.register(ReminderDelivery)
class ReminderDeliveryAdmin(admin.ModelAdmin):
    list_display = ['email', 'state', 'processed_at', 'batch']
    list_filter = ['state']
    search_fields = ['email']
    readonly_fields = ['batch', 'fellow', 'email', 'body', 'state', 'processed_at']
    def has_add_permission(self, request):
        return False
    def has_delete_permission(self, request, obj=None):
        return False
