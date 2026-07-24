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
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='fellow_profile'
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

    assigned_to = models.ForeignKey(Fellow, on_delete=models.CASCADE, related_name='tasks')
    cohort = models.ForeignKey(Cohort, on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks')

    icon = models.CharField(max_length=20, blank=True)
    color = models.CharField(max_length=10, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    due_date = models.DateField(null=True, blank=True)

    google_task_id = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"[{self.get_status_display()}] {self.title}"

    class Meta:
        ordering = ['-created_at']


class MeetingAvailability(models.Model):
    fellow = models.ForeignKey(Fellow, on_delete=models.CASCADE, related_name='availability_slots')
    day_of_week = models.PositiveSmallIntegerField()
    hour = models.PositiveSmallIntegerField()
    is_available = models.BooleanField(default=False)

    def __str__(self):
        days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
        return f"{self.fellow} — {days[self.day_of_week]} {self.hour}:00"

    class Meta:
        unique_together = ['fellow', 'day_of_week', 'hour']
        ordering = ['day_of_week', 'hour']


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