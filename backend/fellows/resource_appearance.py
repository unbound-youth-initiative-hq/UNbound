import re
from urllib.parse import urlsplit

from django.db.models import TextChoices


class ResourceType(TextChoices):
    FOLDER = 'folder', 'Folder'
    FILE = 'file', 'File'
    FORM = 'form', 'Form'
    WEBSITE = 'website', 'Website'
    LINK = 'link', 'Link'


DRIVE_HOSTS = ('drive.google.com', 'docs.google.com')
TYPE_RULES = (
    (ResourceType.FORM, ('forms.gle',), r'^'),
    (ResourceType.FORM, ('docs.google.com',), r'^/forms/'),
    (ResourceType.FOLDER, DRIVE_HOSTS, r'^/(?:drive/)?(?:u/\d+/)?folders/[A-Za-z0-9_-]+(?:/|$)'),
    (ResourceType.FILE, DRIVE_HOSTS, r'^/(?:file|document|spreadsheets|presentation|forms|drawings|vids)/(?:u/\d+/)?d/[A-Za-z0-9_-]+(?:/|$)'),
    (ResourceType.LINK, DRIVE_HOSTS, r'^'),
)
ICONS = {
    'folder': ('Folder', 'fa-solid fa-folder file-folder'),
    'file': ('File', 'fa-regular fa-file file-doc'),
    'form': ('Checklist', 'fa-solid fa-list-check file-doc'),
    'link': ('Link', 'fa-solid fa-link file-generic'),
    'guide': ('Guide', 'fa-solid fa-book file-doc'),
    'calendar': ('Calendar', 'fa-solid fa-calendar-days file-doc'),
    'video': ('Video', 'fa-solid fa-video file-video'),
}
DEFAULT_ICONS = {
    ResourceType.FOLDER: 'folder',
    ResourceType.FILE: 'file',
    ResourceType.FORM: 'form',
    ResourceType.WEBSITE: 'link',
    ResourceType.LINK: 'link',
}
RESOURCE_PREVIEW_OPTIONS = {
    'rules': TYPE_RULES,
    'types': dict(ResourceType.choices),
    'defaults': DEFAULT_ICONS,
    'icons': {key: css_class for key, (_, css_class) in ICONS.items()},
}


def infer_resource_type(url):
    try:
        parts = urlsplit(url)
    except ValueError:
        return ResourceType.LINK
    if not parts.hostname:
        return ResourceType.LINK
    for kind, hosts, pattern in TYPE_RULES:
        if parts.hostname in hosts and re.match(pattern, parts.path):
            return kind
    return ResourceType.WEBSITE
