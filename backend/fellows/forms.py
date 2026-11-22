from io import BytesIO
from urllib.parse import parse_qs, urlsplit

from django import forms
from django.core import signing
from django.db.models import Count, Max
from PIL import Image, UnidentifiedImageError

from .models import AvailabilityRequest, Badge, Cohort, CohortDriveLink, SharedDriveResource


class InviteBatchForm(forms.Form):
    audience = forms.ChoiceField(
        choices=[('', 'Choose an audience'), ('cohort', 'A specific cohort'), ('unassigned', 'Unassigned fellows')],
    )
    cohort = forms.ModelChoiceField(queryset=Cohort.objects.filter(is_active=True), required=False)

    def clean(self):
        data = super().clean()
        if data.get('audience') == 'cohort' and not data.get('cohort'):
            self.add_error('cohort', 'Choose an active cohort.')
        elif data.get('audience') == 'unassigned':
            data['cohort'] = None
        return data


class AvailabilityRequestAdminForm(forms.ModelForm):
    reset_snapshot = forms.CharField(required=False, widget=forms.HiddenInput)
    confirm_response_reset = forms.BooleanField(
        required=False, label='Reset existing availability if I change the meeting window',
        help_text='The saved responses will be cleared and linked tasks will reopen. To preserve them, create a new poll instead.',
    )
    snapshot_salt = 'whenbound-window-reset'
    window_fields = ('start_date', 'end_date', 'start_hour', 'end_hour')

    class Meta:
        model = AvailabilityRequest
        fields = '__all__'
        labels = {
            'start_date': 'Earliest meeting date',
            'end_date': 'Latest meeting date',
            'start_hour': 'First selectable hour',
            'end_hour': 'End hour (exclusive)',
            'deadline': 'Respond by',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and not self.is_bound:
            snapshot = self.response_snapshot()
            self.initial['reset_snapshot'] = signing.dumps(snapshot, salt=self.snapshot_salt)
            self.set_reset_help(snapshot)

    def response_snapshot(self):
        submissions = self.instance.submissions.aggregate(count=Count('pk'), latest=Max('submitted_at'))
        slots = self.instance.availability_slots.aggregate(count=Count('pk'), last_id=Max('pk'))
        return [
            self.instance.pk, *[str(getattr(self.instance, field)) for field in self.window_fields],
            submissions['count'], str(submissions['latest']), slots['count'], slots['last_id'],
        ]

    def set_reset_help(self, snapshot):
        response_count = snapshot[-4]
        help_text = self.fields['confirm_response_reset'].help_text
        self.fields['confirm_response_reset'].help_text = f'{response_count} submitted so far. {help_text}'

    def clean(self):
        data = super().clean()
        if not self.instance.pk or not set(self.window_fields).intersection(self.changed_data):
            return data
        snapshot = self.response_snapshot()
        if not (snapshot[-4] or snapshot[-2]):
            return data
        try:
            confirmed_snapshot = signing.loads(data.get('reset_snapshot') or '', salt=self.snapshot_salt)
        except signing.BadSignature:
            confirmed_snapshot = None
        if data.get('confirm_response_reset') and confirmed_snapshot == snapshot:
            return data
        self.set_reset_help(snapshot)
        # Retain entered dates but require a fresh acknowledgment of the current responses.
        self.data = self.data.copy()
        self.data[self.add_prefix('reset_snapshot')] = signing.dumps(snapshot, salt=self.snapshot_salt)
        self.data.pop(self.add_prefix('confirm_response_reset'), None)
        self.add_error('confirm_response_reset', 'Review the current response count and confirm the reset to change the window.')
        return data


class DrivePinForm(forms.ModelForm):
    class Meta:
        model = CohortDriveLink
        fields = ['title', 'url']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'input-field'}),
            'url': forms.URLInput(attrs={'class': 'input-field', 'placeholder': 'https://drive.google.com/…'}),
        }

    def clean_url(self):
        url = self.cleaned_data['url']
        parts = urlsplit(url)
        if parts.netloc in {'drive.google.com', 'docs.google.com'}:
            if CohortDriveLink(url=url).kind in {'Folder', 'File', 'Form'}:
                return url
            if parts.netloc == 'drive.google.com' and parts.path == '/open' and parse_qs(parts.query).get('id'):
                return url
        raise forms.ValidationError('Paste the sharing link for a Google Drive file or folder.')


class SharedDriveResourceForm(forms.ModelForm):
    class Meta:
        model = SharedDriveResource
        fields = ['title', 'url', 'description', 'audience', 'cohorts', 'is_published']

    def clean(self):
        cleaned = super().clean()
        audience = cleaned.get('audience')
        if audience == SharedDriveResource.Audience.SELECTED and 'cohorts' in cleaned and not cleaned['cohorts']:
            self.add_error('cohorts', 'Choose at least one cohort for this resource.')
        elif audience == SharedDriveResource.Audience.ALL and 'cohorts' in cleaned:
            cleaned['cohorts'] = []
        return cleaned


class BadgeAdminForm(forms.ModelForm):
    custom_icon = forms.FileField(required=False, help_text=(
        'Optional PNG, JPEG or WebP, up to 2 MB and 2048 × 2048 pixels. '
        'An uploaded icon takes priority over the artwork selection.'
    ))
    remove_custom_icon = forms.BooleanField(required=False, label='Remove uploaded icon')

    class Meta:
        model = Badge
        fields = '__all__'

    def clean_custom_icon(self):
        upload = self.cleaned_data['custom_icon']
        if not upload:
            return None
        if upload.size > 2 * 1024 * 1024:
            raise forms.ValidationError('Choose an image no larger than 2 MB.')
        try:
            with Image.open(upload, formats=('PNG', 'JPEG', 'WEBP')) as image:
                if max(image.size) > 2048:
                    raise forms.ValidationError('Choose an image no larger than 2048 × 2048 pixels.')
                image.thumbnail((192, 192), Image.Resampling.LANCZOS)
                pixels = image.convert('RGBA')
                pixels.info.clear()
                output = BytesIO()
                pixels.save(output, 'PNG')
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as error:
            raise forms.ValidationError('Choose a readable PNG, JPEG or WebP image.') from error
        return output.getvalue()

    def save(self, commit=True):
        image = self.cleaned_data['custom_icon']
        if image or self.cleaned_data['remove_custom_icon']:
            self.instance.icon_png = image or b''
        return super().save(commit=commit)
