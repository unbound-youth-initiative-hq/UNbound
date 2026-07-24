from django.contrib import admin
from .models import Chapter, Cohort, SDG, Fellow, Task, MeetingAvailability, Badge, FellowBadge, InviteCode


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


@admin.register(Fellow)
class FellowAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'role', 'chapter', 'cohort', 'get_current_phase', 'xp_points']
    list_filter = ['role', 'chapter', 'cohort']
    search_fields = ['user__first_name', 'user__last_name', 'user__email']
    inlines = [TaskInline, FellowBadgeInline]

    @admin.display(description='Current Phase')
    def get_current_phase(self, obj):
        return obj.cohort.current_phase if obj.cohort else '-'


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ['title', 'assigned_to', 'scope', 'status', 'source', 'due_date', 'created_at']
    list_filter = ['status', 'scope', 'source']
    search_fields = ['title', 'description']
    list_editable = ['status']


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ['name', 'trigger_type', 'required_task_count', 'required_phase', 'xp_reward', 'color', 'order']
    ordering = ['order']


@admin.register(MeetingAvailability)
class MeetingAvailabilityAdmin(admin.ModelAdmin):
    list_display = ['fellow', 'day_of_week', 'hour', 'is_available']
    list_filter = ['day_of_week', 'is_available']