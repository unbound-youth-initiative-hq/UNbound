"""Real allauth callbacks with synthetic Google data and isolated portal sessions."""
from datetime import date
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount, SocialLogin, SocialToken
from django.contrib.auth import SESSION_KEY, get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Cohort, Fellow, InviteCode


@override_settings(SOCIALACCOUNT_PROVIDERS={
    'google': {'APP': {'client_id': 'test-client', 'secret': 'test-secret', 'key': ''},
               'SCOPE': ['email', 'profile']},
})
class AuthenticationSessionTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username='operator', email='operator@example.com', password='test-password',
        )
        self.cohort = Cohort.objects.create(
            name='Pilot', start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
        )

    def google_identity(self, email, uid='test-google-uid', verified=True):
        return SocialLogin(
            user=get_user_model()(email=email, first_name='Google Fellow'),
            account=SocialAccount(provider='google', uid=uid,
                                  extra_data={'email': email, 'email_verified': verified}),
            email_addresses=[EmailAddress(email=email, verified=verified, primary=True)],
        )

    def callback(self, identity, process='login'):
        response = self.client.get(reverse('google_login'), {'process': process, 'next': '/dashboard/'})
        self.assertEqual(response.status_code, 302)
        state = parse_qs(urlsplit(response['Location']).query)['state'][0]
        def complete_login(adapter, request, app, token, **kwargs):
            identity.provider = adapter.get_provider()
            return identity

        with patch('allauth.socialaccount.providers.google.views.GoogleOAuth2Adapter.get_access_token_data',
                   return_value={'access_token': 'synthetic-access-token', 'expires_in': 3600,
                                 'refresh_token': 'synthetic-refresh-token'}), \
             patch('allauth.socialaccount.providers.google.views.GoogleOAuth2Adapter.complete_login',
                   autospec=True, side_effect=complete_login):
            return self.client.get(reverse('google_callback'), {'state': state, 'code': 'synthetic-code'})

    def pending_invitation(self):
        invitation = InviteCode.objects.create(cohort=self.cohort, role=Fellow.Role.FELLOW)
        session = self.client.session
        session['verified_invite_code_id'] = invitation.pk
        session.save()
        return invitation

    def portal_user(self, name='fellow'):
        user = get_user_model().objects.create_user(name, email=f'{name}@example.com')
        Fellow.objects.create(user=user, cohort=self.cohort)
        self.client.force_login(user)
        return user

    def assert_portal_user(self, user):
        self.assertEqual(int(self.client.session[SESSION_KEY]), user.pk)

    def test_admin_session_does_not_turn_student_registration_into_account_linking(self):
        response = self.client.post('/admin/login/', {'username': self.admin.username, 'password': 'test-password', 'next': '/admin/'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get('/admin/').status_code, 200)
        invitation = self.pending_invitation()
        response = self.callback(self.google_identity('student@example.com'))
        self.assertRedirects(response, '/dashboard/', fetch_redirect_response=False)
        student = SocialAccount.objects.get(uid='test-google-uid').user
        self.assertNotEqual(student.pk, self.admin.pk)
        self.assertFalse(student.is_staff)
        self.assertEqual(student.fellow_profile.cohort, self.cohort)
        self.assertEqual(self.client.get('/admin/').status_code, 200)
        self.assertFalse(Fellow.objects.filter(user=self.admin).exists())
        self.assert_portal_user(student)
        invitation.refresh_from_db()
        self.assertEqual(invitation.times_used, 1)

    def test_same_email_does_not_implicitly_connect_a_google_identity(self):
        user = self.portal_user()
        invitation = self.pending_invitation()
        response = self.callback(self.google_identity(user.email))
        self.assertEqual(response.status_code, 302)
        self.assert_portal_user(user)
        self.assertFalse(SocialAccount.objects.exists())
        invitation.refresh_from_db()
        self.assertEqual(invitation.times_used, 0)

    def test_staff_portal_identity_is_not_automatically_enrolled(self):
        self.client.force_login(self.admin)
        response = self.callback(self.google_identity(self.admin.email), process='connect')
        self.assertRedirects(response, reverse('register_code'), fetch_redirect_response=False)
        self.assert_portal_user(self.admin)
        self.assertFalse(Fellow.objects.filter(user=self.admin).exists())
        self.assertFalse(SocialAccount.objects.exists())

    def test_existing_portal_identity_explicitly_connects_verified_google_account(self):
        user = self.portal_user()
        response = self.callback(self.google_identity('chosen-google@example.com'), process='connect')
        self.assertRedirects(response, '/dashboard/', fetch_redirect_response=False)
        self.assert_portal_user(user)
        self.assertEqual(SocialAccount.objects.get(uid='test-google-uid').user_id, user.pk)
        self.assertFalse(SocialToken.objects.filter(account__user=user).exists())

    def test_linked_portal_identity_repeated_login_requires_no_invitation(self):
        user = self.portal_user()
        SocialAccount.objects.create(provider='google', uid='test-google-uid', user=user)
        response = self.callback(self.google_identity(user.email))
        self.assertRedirects(response, '/dashboard/', fetch_redirect_response=False)
        self.assert_portal_user(user)
        self.assertEqual(SocialAccount.objects.count(), 1)
        self.assertEqual(InviteCode.objects.count(), 0)

    def test_different_implicit_identity_preserves_portal_and_pending_invitation(self):
        user = self.portal_user()
        invitation = self.pending_invitation()
        response = self.callback(self.google_identity('different@example.com'))
        self.assertEqual(response.status_code, 302)
        self.assert_portal_user(user)
        self.assertFalse(SocialAccount.objects.exists())
        invitation.refresh_from_db()
        self.assertEqual(invitation.times_used, 0)
        self.assertEqual(self.client.session.get('verified_invite_code_id'), invitation.pk)

    def test_explicit_connect_rejects_unverified_identity(self):
        user = self.portal_user()
        response = self.callback(self.google_identity('chosen-google@example.com', verified=False), process='connect')
        self.assertEqual(response.status_code, 302)
        self.assert_portal_user(user)
        self.assertFalse(SocialAccount.objects.exists())

    def test_google_identity_owned_elsewhere_cannot_replace_or_link_current_user(self):
        other = get_user_model().objects.create_user('other', email='other@example.com')
        SocialAccount.objects.create(provider='google', uid='already-owned', user=other)
        user = self.portal_user()
        response = self.callback(self.google_identity(other.email, uid='already-owned'), process='connect')
        self.assertEqual(response.status_code, 302)
        self.assert_portal_user(user)
        self.assertEqual(SocialAccount.objects.get(uid='already-owned').user_id, other.pk)
        self.assertFalse(SocialAccount.objects.filter(user=user).exists())

    def test_anonymous_signup_persists_profile_then_login_needs_no_code(self):
        invitation = self.pending_invitation()
        response = self.callback(self.google_identity('new-fellow@example.com'))
        self.assertRedirects(response, '/dashboard/', fetch_redirect_response=False)
        account = SocialAccount.objects.get(uid='test-google-uid')
        self.assert_portal_user(account.user)
        self.assertEqual(account.user.fellow_profile.cohort, self.cohort)
        self.assertFalse(account.user.is_staff)
        invitation.refresh_from_db()
        self.assertEqual(invitation.times_used, 1)
        self.client.logout()
        response = self.callback(self.google_identity('new-fellow@example.com'))
        self.assertRedirects(response, '/dashboard/', fetch_redirect_response=False)
        self.assert_portal_user(account.user)
        invitation.refresh_from_db()
        self.assertEqual(invitation.times_used, 1)

    def test_anonymous_new_identity_without_invitation_is_not_registered(self):
        response = self.callback(self.google_identity('not-invited@example.com'))
        self.assertRedirects(response, reverse('register_code'), fetch_redirect_response=False)
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertFalse(SocialAccount.objects.exists())
        self.assertFalse(get_user_model().objects.filter(email='not-invited@example.com').exists())

    def test_linked_identity_without_profile_can_login_then_explicitly_enroll(self):
        user = get_user_model().objects.create_user('legacy', email='legacy@example.com')
        SocialAccount.objects.create(provider='google', uid='test-google-uid', user=user)
        response = self.callback(self.google_identity(user.email))
        self.assertEqual(response.status_code, 302)
        self.assert_portal_user(user)
        invitation = InviteCode.objects.create(cohort=self.cohort)
        response = self.client.post(reverse('register_code'), {'invite_code': invitation.code})
        self.assertEqual(parse_qs(urlsplit(response['Location']).query)['process'], ['connect'])
        response = self.callback(self.google_identity(user.email), process='connect')
        self.assertRedirects(response, '/dashboard/', fetch_redirect_response=False)
        self.assertEqual(user.fellow_profile.cohort, self.cohort)
        invitation.refresh_from_db()
        self.assertEqual(invitation.times_used, 1)

    def test_registered_portal_user_cannot_redeem_another_invitation(self):
        user = self.portal_user()
        invitation = InviteCode.objects.create(cohort=self.cohort)
        response = self.client.post(reverse('register_code'), {'invite_code': invitation.code})
        self.assertRedirects(response, '/dashboard/', fetch_redirect_response=False)
        invitation.refresh_from_db()
        self.assertEqual(invitation.times_used, 0)
