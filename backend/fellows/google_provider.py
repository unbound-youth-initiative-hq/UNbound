"""Keep launch sign-in identity-only, including allauth's dynamic OAuth options."""
from allauth.socialaccount.providers.google.provider import GoogleProvider
from django.conf import settings


class UnboundGoogleProvider(GoogleProvider):
    @classmethod
    def get_package(cls):
        # Reuse allauth's maintained Google login/callback URLs and validation.
        return 'allauth.socialaccount.providers.google'

    def get_scope(self):
        if not settings.GOOGLE_INTEGRATIONS_ENABLED:
            return ['openid', 'email', 'profile']
        return super().get_scope()

    def get_scope_from_request(self, request):
        if not settings.GOOGLE_INTEGRATIONS_ENABLED:
            return self.get_scope()
        return super().get_scope_from_request(request)

    def get_auth_params(self):
        if not settings.GOOGLE_INTEGRATIONS_ENABLED:
            return {'access_type': 'online', 'prompt': 'select_account'}
        return super().get_auth_params()

    def get_auth_params_from_request(self, request, action):
        if not settings.GOOGLE_INTEGRATIONS_ENABLED:
            return self.get_auth_params()
        return super().get_auth_params_from_request(request, action)
