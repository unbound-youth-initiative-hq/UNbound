from django.db import models
from django.conf import settings
from django.utils import timezone


def generate_random_code():
    import secrets
    import string
    chars = string.ascii_uppercase + string.digits
    part1 = ''.join(secrets.choice(chars) for _ in range(4))
    part2 = ''.join(secrets.choice(chars) for _ in range(4))
    return f"UNBOUND-{part1}-{part2}"


class SDG(models.Model):
    """UN Sustainable Development Goals (SDGs 1-17)."""
    code = models.PositiveIntegerField(unique=True, help_text="UN Goal Number (1-17)")
    name = models.CharField(max_length=150)
    color = models.CharField(max_length=20, default='#00B4D8')

    def __str__(self):
        return f"SDG {self.code}: {self.name}"

    class Meta:
        ordering = ['code']
        verbose_name = "SDG / UN Goal"
        verbose_name_plural = "SDGs / UN Goals"


class Chapter(models.Model):
    name = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    country_code = models.CharField(max_length=5)
    timezone = models.CharField(max_length=50, default='America/Monterrey')
    founded_year = models.PositiveIntegerField(null=True, blank=True)

    def __str__(self):
        return f"{self.name}, {self.country_code}"

    class Meta:
        ordering = ['name']


class Cohort(models.Model):
    """Cohort holding shared project data, status phase, and UN goals."""
    name = models.CharField(max_length=100)
    project_name = models.CharField(max_length=200, blank=True, help_text="Name of the cohort's project")
    project_description = models.TextField(blank=True, help_text="Detailed summary of the cohort's project")
    current_phase = models.CharField(max_length=50, default='Orbit of Ideas', help_text="Current phase/status of the cohort project")
    selected_sdgs = models.ManyToManyField(SDG, blank=True, related_name='cohorts', help_text="Selected UN Sustainable Development Goals")

    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        if self.project_name:
            return f"Cohort {self.name} — {self.project_name}"
        return f"Cohort {self.name}"

    class Meta:
        ordering = ['-start_date']


class InviteCode(models.Model):
    code = models.CharField(
        max_length=50, 
        unique=True, 
        default=generate_random_code, 
        help_text="Unique invite code provided by Fellowship Execs."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True, help_text="Optional expiration date for this code.")
    max_uses = models.PositiveIntegerField(default=1, help_text="Number of times this code can be used (default: 1).")
    times_used = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, help_text="Deactivate code manually if needed.")

    cohort = models.ForeignKey('Cohort', on_delete=models.SET_NULL, null=True, blank=True, help_text="Cohort automatically assigned upon registration.")
    role = models.CharField(
        max_length=10, 
        choices=[('fellow', 'Fellow'), ('mentor', 'Mentor'), ('exec', 'Executive')], 
        default='fellow'
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_invite_codes')

    def is_valid(self):
        if not self.is_active:
            return False, "This invite code has been deactivated."
        if self.times_used >= self.max_uses:
            return False, "This invite code has already reached its maximum usage limit."
        if self.expires_at and timezone.now() > self.expires_at:
            return False, "This invite code has expired."
        return True, "Valid code"

    def mark_as_used(self, user):
        self.times_used += 1
        if self.times_used >= self.max_uses:
            self.is_active = False
        self.save()

    def __str__(self):
        status = "Active" if self.is_active else "Inactive"
        return f"{self.code} ({self.times_used}/{self.max_uses} used) - {status}"

    class Meta:
        ordering = ['-created_at']


class Fellow(models.Model):
    class AccentPalette(models.TextChoices):
        OCEAN = 'ocean', 'Ocean'
        SKY = 'sky', 'Sky'
        CORAL = 'coral', 'Coral'
        VIOLET = 'violet', 'Violet'
        MINT = 'mint', 'Mint'
        FOREST = 'forest', 'Forest'
        ROSE = 'rose', 'Rose'
        AMBER = 'amber', 'Amber'

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='fellow_profile'
    )
    accent_palette = models.CharField(
        max_length=12,
        choices=AccentPalette.choices,
        default=AccentPalette.OCEAN,
    )
    chapter = models.ForeignKey(
        Chapter,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='fellows'
    )
    cohort = models.ForeignKey(
        Cohort,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='fellows'
    )

    class Role(models.TextChoices):
        FELLOW = 'fellow', 'Fellow'
        MENTOR = 'mentor', 'Mentor'
        EXEC = 'exec', 'Executive'

    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.FELLOW,
    )

    xp_points = models.PositiveIntegerField(default=0)

    google_access_token = models.TextField(blank=True)
    google_refresh_token = models.TextField(blank=True)
    google_token_expiry = models.DateTimeField(null=True, blank=True)

    selected_drive_folder_id = models.CharField(max_length=255, blank=True)
    selected_drive_folder_name = models.CharField(max_length=255, blank=True)

    @property
    def project_name(self):
        return self.cohort.project_name if self.cohort else ""

    @property
    def project_description(self):
        return self.cohort.project_description if self.cohort else ""

    @property
    def current_phase(self):
        return self.cohort.current_phase if self.cohort else "Orbit of Ideas"

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.get_role_display()})"

    class Meta:
        ordering = ['user__last_name', 'user__first_name']


def availability_task_visibility_filter(fellow):
    """Return a Task queryset filter for availability requests visible to this fellow."""
    if (
        not fellow
        or fellow.role != Fellow.Role.FELLOW
        or not fellow.user.is_active
    ):
        return models.Q(availability_request__isnull=True)

    request_targets_fellow = (
        models.Q(availability_request__assign_to_all=True)
        | models.Q(availability_request__cohort__isnull=True)
    )
    if fellow.cohort_id:
        request_targets_fellow |= models.Q(
            availability_request__cohort_id=fellow.cohort_id
        )

    return models.Q(availability_request__isnull=True) | (
        models.Q(availability_request__is_active=True)
        & request_targets_fellow
    )


class Task(models.Model):
    class Scope(models.TextChoices):
        TEAM = 'team', 'Team'
        PERSONAL = 'personal', 'Personal'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        IN_PROGRESS = 'in_progress', 'In Progress'
        COMPLETE = 'complete', 'Complete'

    class Source(models.TextChoices):
        UNBOUND = 'unbound', 'Assigned by UNbound'
        SELF = 'self', 'Self-created'

    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    scope = models.CharField(max_length=10, choices=Scope.choices, default=Scope.PERSONAL)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.SELF)

    assigned_to = models.ForeignKey(Fellow, on_delete=models.CASCADE, related_name='tasks', null=True, blank=True)
    cohort = models.ForeignKey(Cohort, on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks')

    icon = models.CharField(max_length=20, blank=True)
    color = models.CharField(max_length=10, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    due_date = models.DateField(null=True, blank=True)

    google_task_id = models.CharField(max_length=200, blank=True)
    availability_request = models.ForeignKey(
        'AvailabilityRequest',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='tasks'
    )

    @classmethod
    def assign_task(
        cls,
        title,
        description='',
        scope=Scope.PERSONAL,
        due_date=None,
        target_mode='fellow',
        fellow=None,
        cohort=None,
        source=Source.UNBOUND,
        icon='',
        color='',
        availability_request=None,
    ):
        """
        Creates and assigns tasks according to the chosen distribution mode.
        - 'fellow': Single task for specific fellow.
        - 'cohort_team': Single team task for the cohort (one completion completes for cohort).
        - 'cohort_individual': Personal task for each member in the cohort.
        - 'all_cohorts_team': 1 shared team task per cohort with active fellows.
        - 'all_fellows_individual': 1 personal task per active fellow.
        """
        created_tasks = []
        eligible_fellows = Fellow.objects.filter(
            role=Fellow.Role.FELLOW,
            user__is_active=True,
        )
        default_icon = icon or ('fa-pen-to-square' if scope == cls.Scope.TEAM else 'fa-check')
        default_color = color or ('#00B4D8' if scope == cls.Scope.TEAM else '#e0a009')

        if target_mode == 'all_cohorts_team':
            # A shared assignment is represented by one task row per cohort.
            # Limit those rows to cohorts that currently have active fellows.
            cohorts = Cohort.objects.filter(fellows__in=eligible_fellows).distinct()
            for c in cohorts:
                t = cls.objects.create(
                    title=title,
                    description=description,
                    scope=cls.Scope.TEAM,
                    source=source,
                    cohort=c,
                    assigned_to=None,
                    due_date=due_date,
                    icon=default_icon,
                    color=default_color,
                    availability_request=availability_request,
                )
                created_tasks.append(t)

        elif target_mode == 'all_fellows_individual':
            for f in eligible_fellows:
                t = cls.objects.create(
                    title=title,
                    description=description,
                    scope=cls.Scope.PERSONAL,
                    source=source,
                    cohort=f.cohort,
                    assigned_to=f,
                    due_date=due_date,
                    icon=default_icon,
                    color=default_color,
                    availability_request=availability_request,
                )
                created_tasks.append(t)

        elif target_mode == 'cohort_team' and cohort:
            t = cls.objects.create(
                title=title,
                description=description,
                scope=cls.Scope.TEAM,
                source=source,
                cohort=cohort,
                assigned_to=None,
                due_date=due_date,
                icon=default_icon,
                color=default_color,
                availability_request=availability_request,
            )
            created_tasks.append(t)

        elif target_mode == 'cohort_individual' and cohort:
            for f in eligible_fellows.filter(cohort=cohort):
                t = cls.objects.create(
                    title=title,
                    description=description,
                    scope=cls.Scope.PERSONAL,
                    source=source,
                    cohort=cohort,
                    assigned_to=f,
                    due_date=due_date,
                    icon=default_icon,
                    color=default_color,
                    availability_request=availability_request,
                )
                created_tasks.append(t)

        elif fellow:
            t = cls.objects.create(
                title=title,
                description=description,
                scope=scope,
                source=source,
                cohort=cohort or fellow.cohort,
                assigned_to=fellow,
                due_date=due_date,
                icon=default_icon,
                color=default_color,
                availability_request=availability_request,
            )
            created_tasks.append(t)

        return created_tasks

    def __str__(self):
        return f"[{self.get_status_display()}] {self.title}"

    class Meta:
        ordering = ['-created_at']


class AvailabilityRequest(models.Model):
    """When to meet / availability request created by admin for a specific cohort or all fellows."""
    title = models.CharField(max_length=200, help_text="e.g. Sprint 3 Sync Availability")
    description = models.TextField(blank=True, help_text="Instructions or context for the fellows.")
    start_date = models.DateField(help_text="Start date of the availability window.")
    end_date = models.DateField(help_text="End date of the availability window.")
    start_hour = models.PositiveSmallIntegerField(default=9, help_text="Starting hour (0-23, default 9 for 9 AM).")
    end_hour = models.PositiveSmallIntegerField(default=18, help_text="Ending hour (0-23, default 18 for 6 PM).")

    cohort = models.ForeignKey(
        'Cohort',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='availability_requests',
        help_text="Target cohort. Leave blank if assigning to all fellows."
    )
    assign_to_all = models.BooleanField(
        default=False,
        help_text="If checked, this request applies to all active fellows regardless of cohort."
    )
    deadline = models.DateField(
        null=True,
        blank=True,
        help_text="Optional submission deadline for fellows."
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Active requests are visible in the fellows' Meeting Hub."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_availability_requests'
    )

    def target_fellows(self):
        """Active fellow accounts who should receive this availability request."""
        target_fellows = Fellow.objects.filter(
            role=Fellow.Role.FELLOW,
            user__is_active=True,
        )
        if not self.assign_to_all and self.cohort_id:
            target_fellows = target_fellows.filter(cohort_id=self.cohort_id)
        return target_fellows.select_related('user', 'cohort')

    def create_tasks_for_fellows(self):
        """Create or ensure one UNbound availability task per active target fellow."""
        if not self.is_active:
            return []

        created_tasks = []
        for fellow in self.target_fellows():
            task, _ = Task.objects.get_or_create(
                assigned_to=fellow,
                availability_request=self,
                defaults={
                    'title': f"When2meet: {self.title}",
                    'description': self.description or f"Submit your availability for {self.start_date.strftime('%b %d')} – {self.end_date.strftime('%b %d')}.",
                    'scope': Task.Scope.PERSONAL,
                    'status': Task.Status.PENDING,
                    'source': Task.Source.UNBOUND,
                    'icon': 'fa-calendar-check',
                    'color': '#00B4D8',
                    'due_date': self.deadline or self.start_date,
                    'cohort': fellow.cohort,
                }
            )
            created_tasks.append(task)
        return created_tasks

    def __str__(self):
        target = "All Cohorts" if self.assign_to_all or not self.cohort else f"Cohort {self.cohort.name}"
        return f"{self.title} ({self.start_date} to {self.end_date}) — {target}"

    class Meta:
        ordering = ['-created_at']
        verbose_name = "When to Meet Request"
        verbose_name_plural = "When to Meet Requests"


class MeetingAvailability(models.Model):
    availability_request = models.ForeignKey(
        AvailabilityRequest,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='availability_slots'
    )
    fellow = models.ForeignKey(Fellow, on_delete=models.CASCADE, related_name='availability_slots')
    date = models.DateField(null=True, blank=True)
    day_of_week = models.PositiveSmallIntegerField(null=True, blank=True)
    hour = models.PositiveSmallIntegerField()
    is_available = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if self.date and self.day_of_week is None:
            self.day_of_week = (self.date.weekday() + 1) % 7
        super().save(*args, **kwargs)

    def __str__(self):
        if self.date:
            return f"{self.fellow} — {self.date} {self.hour}:00 ({'Free' if self.is_available else 'Busy'})"
        days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
        dow = self.day_of_week if self.day_of_week is not None else 0
        return f"{self.fellow} — {days[dow]} {self.hour}:00"

    class Meta:
        ordering = ['date', 'day_of_week', 'hour']
        constraints = [
            models.UniqueConstraint(
                fields=['availability_request', 'fellow', 'date', 'hour'],
                name='unique_availability_request_slot'
            ),
            models.UniqueConstraint(
                fields=['fellow', 'day_of_week', 'hour'],
                condition=models.Q(availability_request__isnull=True),
                name='unique_legacy_availability_slot'
            )
        ]


class Badge(models.Model):
    class TriggerType(models.TextChoices):
        TASK_COUNT = 'task_count', 'Completed Task Count'
        PROJECT_PHASE = 'project_phase', 'Project Phase Reached'
        AVAILABILITY = 'availability', 'Meeting Availability Synced'
        MANUAL = 'manual', 'Manual / Admin Awarded'

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True, blank=True)
    description = models.TextField()
    color = models.CharField(max_length=20, default='#00B4D8')
    icon_class = models.CharField(max_length=50, default='fa-award')
    order = models.PositiveIntegerField(default=0)

    trigger_type = models.CharField(max_length=20, choices=TriggerType.choices, default=TriggerType.MANUAL)
    required_task_count = models.PositiveIntegerField(default=0, help_text="Number of completed tasks required to unlock.")
    required_phase = models.CharField(max_length=50, blank=True, help_text="Phase required (e.g. Prototype, Graduation).")
    xp_reward = models.PositiveIntegerField(default=100, help_text="XP awarded when badge is earned.")

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['order']


class FellowBadge(models.Model):
    fellow = models.ForeignKey(Fellow, on_delete=models.CASCADE, related_name='badges')
    badge = models.ForeignKey('Badge', on_delete=models.CASCADE, related_name='fellow_badges')
    earned = models.BooleanField(default=False)
    progress = models.PositiveIntegerField(default=0)
    earned_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        status = "✓ Earned" if self.earned else f"{self.progress}%"
        return f"{self.fellow} — {self.badge.name} [{status}]"

    class Meta:
        unique_together = ['fellow', 'badge']
