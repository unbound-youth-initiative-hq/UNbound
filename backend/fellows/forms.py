from urllib.parse import parse_qs, urlsplit

from django import forms

from .models import CohortDriveLink, SharedDriveResource


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
