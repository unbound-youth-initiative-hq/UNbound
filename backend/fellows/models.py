import re
from urllib.parse import urlsplit

from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.utils import timezone

from .artwork import BadgeArtwork
from .meeting_timezones import meeting_timezone_choices


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


class Phase(models.Model):
    name = models.CharField(max_length=50, unique=True)
    description = models.CharField(max_length=240, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'pk']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Preserve existing badge rules when staff rename a phase.
        from django.db import transaction
        with transaction.atomic():
            old_name = type(self).objects.filter(pk=self.pk).values_list('name', flat=True).first() if self.pk else None
            super().save(*args, **kwargs)
            if old_name and old_name != self.name:
                Badge.objects.filter(required_phase=old_name).update(required_phase=self.name)


class Cohort(models.Model):
    """Cohort holding shared project data, status phase, and UN goals."""
    name = models.CharField(max_length=100)
    project_name = models.CharField(max_length=200, blank=True, help_text="Name of the cohort's project")
    project_description = models.TextField(blank=True, help_text="Detailed summary of the cohort's project")
    phase = models.ForeignKey(Phase, on_delete=models.PROTECT, null=True, blank=True, related_name='cohorts', verbose_name='Current phase')
    selected_sdgs = models.ManyToManyField(SDG, blank=True, related_name='cohorts', help_text="Selected UN Sustainable Development Goals")

    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)

    @property
    def current_phase(self):
        return self.phase.name if self.phase_id else ''

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({'end_date': 'End date must be on or after the start date.'})

    def __str__(self):
        if self.project_name:
            return f"Cohort {self.name} — {self.project_name}"
        return f"Cohort {self.name}"

    class Meta:
        ordering = ['-start_date']


class DriveResource(models.Model):
    title = models.CharField(max_length=150)
    url = models.URLField(
        'Google sharing link', max_length=2048,
        validators=[RegexValidator(
            r'^https://(?:drive|docs)\.google\.com/',
            'Paste an HTTPS sharing link from drive.google.com or docs.google.com.',
        )],
        help_text='Copy the file or folder link from Google. Share it with the intended fellows in Drive.',
    )

    class Meta:
        abstract = True
        ordering = ['title', 'pk']

    def __str__(self):
        return self.title

    @property
    def kind(self):
        path = urlsplit(self.url).path
        if re.match(r'^/(?:drive/)?(?:u/\d+/)?folders/[\w-]+(?:/|$)', path):
            return 'Folder'
        if re.match(r'^/(?:file|document|spreadsheets|presentation|forms|drawings|vids)/(?:u/\d+/)?d/[\w-]+(?:/|$)', path):
            return 'File'
        return 'Link'


class CohortDriveLink(DriveResource):
    cohort = models.ForeignKey(Cohort, on_delete=models.CASCADE, related_name='drive_links')
    pinned_by = models.ForeignKey('Fellow', on_delete=models.CASCADE, null=True, blank=True, editable=False)

    class Meta(DriveResource.Meta):
        verbose_name = 'Google Drive link'


class SharedDriveResource(DriveResource):
    class Audience(models.TextChoices):
        SELECTED = 'selected', 'Selected cohorts'
        ALL = 'all', 'All cohorts'

    audience = models.CharField(max_length=8, choices=Audience.choices, default=Audience.SELECTED)
    cohorts = models.ManyToManyField(
        Cohort, blank=True, related_name='shared_drive_resources',
        help_text='Choose at least one cohort when the audience is Selected cohorts.',
    )
    is_published = models.BooleanField(default=True)

    class Meta(DriveResource.Meta):
        verbose_name = 'Shared Drive resource'


class ConfirmedMeeting(models.Model):
    cohort = models.ForeignKey(Cohort, on_delete=models.CASCADE, related_name='confirmed_meetings')
    title = models.CharField(max_length=200)
    starts_at = models.DateTimeField(help_text='Enter the start in Monterrey time.')
    ends_at = models.DateTimeField(help_text='Enter the end in Monterrey time.')
    meet_url = models.URLField(
        'Google Meet link', blank=True, max_length=512,
        validators=[RegexValidator(
            r'\Ahttps://meet\.google\.com/(?:[a-z]{3}-[a-z]{4}-[a-z]{3}|lookup/[\w-]+)/?(?:\?[^#\s]*)?\Z',
            'Enter a Google Meet call link.',
        )],
    )
    is_published = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['starts_at', 'pk']
        constraints = [
            models.CheckConstraint(condition=models.Q(ends_at__gt=models.F('starts_at')), name='meeting_ends_after_start'),
        ]

    def clean(self):
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError({'ends_at': 'The meeting must end after it starts.'})

    def __str__(self):
        return self.title


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
        from django.core.exceptions import ValidationError
        eligible = type(self).objects.filter(pk=self.pk, is_active=True, times_used__lt=models.F('max_uses')).filter(models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=timezone.now()))
        if not eligible.update(times_used=models.F('times_used') + 1):
            raise ValidationError('This invitation is no longer available. Request a new code.')
        type(self).objects.filter(pk=self.pk, times_used__gte=models.F('max_uses')).update(is_active=False)
        self.refresh_from_db()

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
    meeting_timezone = models.CharField(
        max_length=64, choices=meeting_timezone_choices, default='America/Monterrey',
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
        return self.cohort.current_phase if self.cohort else ""

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
    due_time = models.TimeField(null=True, blank=True, help_text='Optional Monterrey time for a self-created task.')

    google_task_id = models.CharField(max_length=200, blank=True)
    availability_request = models.ForeignKey(
        'AvailabilityRequest',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='tasks'
    )

    def can_manage(self, user):
        """Only the creator can change or delete a self-created assignment."""
        fellow = getattr(user, 'fellow_profile', None)
        return bool(
            fellow and self.source == self.Source.SELF
            and self.assigned_to_id == fellow.pk
        )

    def affected_fellows(self):
        """Fellows whose progress includes this task, including shared work."""
        audience = models.Q(pk=self.assigned_to_id)
        if self.scope == self.Scope.TEAM and self.cohort_id:
            audience |= models.Q(cohort_id=self.cohort_id)
        return Fellow.objects.filter(
            audience, role=Fellow.Role.FELLOW, user__is_active=True,
        ).select_related('user', 'cohort').order_by('pk')

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
        constraints = [
            models.CheckConstraint(
                condition=models.Q(due_time__isnull=True) | models.Q(due_date__isnull=False, source='self'),
                name='task_due_time_requires_self_task_and_date',
            ),
        ]


class GoogleTaskLink(models.Model):
    """Google task IDs belong to one Google user, even for shared assignments."""
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='google_links')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    google_task_id = models.CharField(max_length=200)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['task', 'user'], name='unique_task_google_user'),
        ]


class AvailabilityRequest(models.Model):
    """WhenBound / availability request created by admin for a specific cohort or all fellows."""
    title = models.CharField(max_length=200, help_text="e.g. Sprint 3 Sync Availability")
    description = models.TextField(blank=True, help_text="Instructions or context for the fellows.")
    start_date = models.DateField(help_text="Start date of the availability window.")
    end_date = models.DateField(help_text="End date of the availability window.")
    start_hour = models.PositiveSmallIntegerField(default=9, help_text="Starting hour (0-23, default 9 for 9 AM).")
    end_hour = models.PositiveSmallIntegerField(default=18, help_text="Ending hour, exclusive (1-24; 24 is midnight).")

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

    def clean(self):
        from datetime import date
        from django.core.exceptions import ValidationError

        errors = {}
        if isinstance(self.start_date, date) and isinstance(self.end_date, date):
            if self.end_date < self.start_date:
                errors['end_date'] = 'End date must be on or after the start date.'
            elif (self.end_date - self.start_date).days >= 42:
                errors['end_date'] = 'A meeting request can cover at most 42 days.'
        if isinstance(self.start_hour, int) and not 0 <= self.start_hour <= 23:
            errors['start_hour'] = 'Choose a starting hour from 0 to 23.'
        if isinstance(self.end_hour, int) and not 1 <= self.end_hour <= 24:
            errors['end_hour'] = 'Choose an ending hour from 1 to 24 (midnight).'
        if isinstance(self.start_hour, int) and isinstance(self.end_hour, int) and self.end_hour <= self.start_hour:
            errors['end_hour'] = 'Ending hour must be after the starting hour.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        from django.db import transaction

        self.full_clean()
        with transaction.atomic():
            previous = type(self).objects.select_for_update().filter(pk=self.pk).first() if self.pk else None
            window_changed = previous and any(
                getattr(previous, name) != getattr(self, name)
                for name in ('start_date', 'end_date', 'start_hour', 'end_hour')
            )
            super().save(*args, **kwargs)
            if window_changed:
                # A response to the previous dates/hours is not a submission to the new window.
                self.availability_slots.all().delete()
                self.submissions.all().delete()
                self.tasks.update(status=Task.Status.PENDING)
            self.create_tasks_for_fellows()

    def target_fellows(self):
        """Active fellow accounts who should receive this availability request."""
        target_fellows = Fellow.objects.filter(
            role=Fellow.Role.FELLOW,
            user__is_active=True,
        )
        if not self.assign_to_all and self.cohort_id:
            target_fellows = target_fellows.filter(cohort_id=self.cohort_id)
        return target_fellows.select_related('user', 'cohort')

    def create_tasks_for_fellows(self, fellow=None):
        """Reconcile active recipients and task metadata without changing valid submissions."""
        from django.db import transaction

        if not self.is_active:
            return []
        with transaction.atomic():
            # All creation paths lock the request, preventing duplicate task creation.
            type(self).objects.select_for_update().get(pk=self.pk)
            targets = self.target_fellows()
            if fellow is not None:
                targets = targets.filter(pk=fellow.pk)
            tasks = []
            for recipient in targets:
                values = {
                    'title': f"WhenBound: {self.title}",
                    'description': self.description or f"Submit your availability for {self.start_date.strftime('%b %d')} – {self.end_date.strftime('%b %d')}.",
                    'scope': Task.Scope.PERSONAL,
                    'source': Task.Source.UNBOUND,
                    'icon': 'fa-calendar-check',
                    'color': '#00B4D8',
                    'due_date': self.deadline or self.start_date,
                    'cohort': recipient.cohort,
                }
                task, created = Task.objects.get_or_create(
                    assigned_to=recipient,
                    availability_request=self,
                    defaults={**values, 'status': Task.Status.PENDING},
                )
                if not created:
                    for name, value in values.items():
                        setattr(task, name, value)
                    task.save(update_fields=list(values))
                tasks.append(task)
            return tasks

    def __str__(self):
        target = "All Cohorts" if self.assign_to_all or not self.cohort else f"Cohort {self.cohort.name}"
        return f"{self.title} ({self.start_date} to {self.end_date}) — {target}"

    class Meta:
        ordering = ['-created_at']
        verbose_name = "WhenBound Request"
        verbose_name_plural = "WhenBound Requests"


class AvailabilitySubmission(models.Model):
    """A submitted response, including a response with no available time slots."""
    availability_request = models.ForeignKey(
        AvailabilityRequest, on_delete=models.CASCADE, related_name='submissions'
    )
    fellow = models.ForeignKey(Fellow, on_delete=models.CASCADE, related_name='availability_submissions')
    submitted_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=['availability_request', 'fellow'], name='unique_availability_submission'
        )]

    def __str__(self):
        return f"{self.fellow} — {self.availability_request.title} (submitted)"


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
    artwork = models.CharField(max_length=20, choices=BadgeArtwork, blank=True)
    icon_png = models.BinaryField(blank=True, default=bytes)
    order = models.PositiveIntegerField(default=0)

    trigger_type = models.CharField(max_length=20, choices=TriggerType.choices, default=TriggerType.MANUAL)
    required_task_count = models.PositiveIntegerField(default=0, help_text="Number of completed tasks required to unlock.")
    required_phase = models.CharField(max_length=50, blank=True, help_text="Phase required for a project-phase award.")
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


class ReminderBatch(models.Model):
    import uuid
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    queued_at = models.DateTimeField(null=True, blank=True)


class ReminderDelivery(models.Model):
    batch = models.ForeignKey(ReminderBatch, on_delete=models.CASCADE, related_name='deliveries')
    fellow = models.ForeignKey(Fellow, on_delete=models.CASCADE)
    email = models.EmailField()
    body = models.TextField()
    state = models.CharField(max_length=12, default='draft', choices=[(s, s.title()) for s in ('draft', 'queued', 'sending', 'sent', 'previewed', 'failed')])
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['batch', 'fellow'], name='unique_reminder_batch_fellow')]
