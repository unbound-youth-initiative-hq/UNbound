from io import BytesIO
from urllib.parse import parse_qs, urlsplit

from django import forms
from PIL import Image, UnidentifiedImageError

from .models import Badge, CohortDriveLink, SharedDriveResource


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
        if CohortDriveLink(url=url).kind != 'Link':
            return url
        parts = urlsplit(url)
        if parts.netloc == 'drive.google.com' and parts.path == '/open' and parse_qs(parts.query).get('id'):
            return url
        raise forms.ValidationError('Paste the sharing link for a Google Drive file or folder.')


class SharedDriveResourceForm(forms.ModelForm):
    class Meta:
        model = SharedDriveResource
        fields = ['title', 'url', 'audience', 'cohorts', 'is_published']

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
