"""Invitation-gated fellow onboarding, independent of Django Admin access."""
from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.internal.flows.connect import do_connect
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme

from .models import Fellow, InviteCode


class UnboundSocialAccountAdapter(DefaultSocialAccountAdapter):
    def _dashboard_redirect(self, request, sociallogin):
        if not Fellow.objects.filter(user=request.user).exists():
            return redirect('register_code')
        target = sociallogin.state.get('next') or '/dashboard/'
        if not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
            target = '/dashboard/'
        return redirect(target)

    def _invitation_required(self, request, message):
        messages.info(request, message)
        raise ImmediateHttpResponse(redirect('register_code'))

    def _ensure_profile(self, request, user):
        """An existing portal account enrolls once, using an explicit invitation."""
        get_user_model().objects.select_for_update().get(pk=user.pk)
        profile = Fellow.objects.filter(user=user).first()
        if profile:
            request.session.pop('verified_invite_code_id', None)
            return profile
        invite_id = request.session.get('verified_invite_code_id')
        if not invite_id:
            self._invitation_required(request, 'Enter your invitation code to finish setting up your fellow profile.')
        try:
            invite = InviteCode.objects.select_for_update().get(pk=invite_id)
            invite.mark_as_used(user)
        except (InviteCode.DoesNotExist, ValidationError, TypeError, ValueError):
            request.session.pop('verified_invite_code_id', None)
            self._invitation_required(request, 'This invitation is no longer available. Please request a new code.')
        profile = Fellow.objects.create(user=user, cohort=invite.cohort, role=invite.role)
        request.session.pop('verified_invite_code_id', None)
        return profile

    def pre_social_login(self, request, sociallogin):
        """Avoid silently replacing a signed-in portal identity or linking by email."""
        current_user = request.user
        if not current_user.is_authenticated:
            # A stored Google identity already identifies its local account. The
            # dashboard handles explicit enrollment if that account has no profile.
            return

        if sociallogin.is_existing:
            if sociallogin.user.pk != current_user.pk:
                messages.error(request, 'That Google account belongs to another UNbound account. Sign out of the portal first to switch accounts.')
                raise ImmediateHttpResponse(redirect('dashboard'))
            if request.session.get('verified_invite_code_id'):
                with transaction.atomic():
                    self._ensure_profile(request, current_user)
            raise ImmediateHttpResponse(self._dashboard_redirect(request, sociallogin))

        verified_emails = [email for email in sociallogin.email_addresses if email.verified]
        explicit_connection = sociallogin.state.get('process') == 'connect'
        if sociallogin.account.provider != 'google' or not verified_emails or not explicit_connection:
            messages.error(request, 'You are already signed into the portal. Use Connect Google to link an account, or sign out of the portal to switch users.')
            raise ImmediateHttpResponse(redirect('dashboard'))

        # Only an explicit portal connection may attach a Google identity to an
        # existing user. Email equality alone never links accounts, and Admin
        # status never grants enrollment or creates a Fellow profile.
        with transaction.atomic():
            self._ensure_profile(request, current_user)
            do_connect(request, sociallogin)
        messages.success(request, 'Google connected to your fellow portal account.')
        raise ImmediateHttpResponse(self._dashboard_redirect(request, sociallogin))

    def is_open_for_signup(self, request, sociallogin):
        invite_code_id = request.session.get('verified_invite_code_id')
        if invite_code_id:
            try:
                invite = InviteCode.objects.get(pk=invite_code_id)
                valid, _ = invite.is_valid()
                if valid:
                    return True
            except (InviteCode.DoesNotExist, TypeError, ValueError):
                pass
        self._invitation_required(request, 'Enter your Fellowship Invitation Code to create your fellow account.')

    def save_user(self, request, sociallogin, form=None):
        invite_id = request.session.get('verified_invite_code_id')
        try:
            with transaction.atomic():
                invite = InviteCode.objects.select_for_update().get(pk=invite_id)
                invite.mark_as_used(None)
                user = super().save_user(request, sociallogin, form)
                Fellow.objects.create(user=user, cohort=invite.cohort, role=invite.role)
        except (InviteCode.DoesNotExist, ValidationError, TypeError, ValueError):
            request.session.pop('verified_invite_code_id', None)
            self._invitation_required(request, 'This invitation is no longer available. Please request a new code.')
        request.session.pop('verified_invite_code_id', None)
        return user


class UnboundAccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        # Public fellow registration uses an invitation and Google. This does
        # not affect the separate Django Admin username/password login.
        return False
