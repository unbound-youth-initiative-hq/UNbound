from allauth.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib import messages
from django.shortcuts import redirect
from .models import InviteCode, Fellow, Cohort


class UnboundSocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request, sociallogin):
        """
        Only allows NEW account signups if a valid invite code has been verified.
        Existing users logging in bypass this check automatically.
        """
        invite_code_id = request.session.get('verified_invite_code_id')
        if invite_code_id:
            try:
                invite = InviteCode.objects.get(id=invite_code_id)
                valid, _ = invite.is_valid()
                if valid:
                    return True
            except InviteCode.DoesNotExist:
                pass

        if request.method == 'POST':
            code_str = request.POST.get('invite_code', '').strip().upper()
            if code_str:
                try:
                    invite = InviteCode.objects.get(code=code_str)
                    valid, msg = invite.is_valid()
                    if valid:
                        request.session['verified_invite_code_id'] = invite.id
                        return True
                    else:
                        messages.error(request, msg)
                except InviteCode.DoesNotExist:
                    messages.error(request, "Invalid invitation code. Please request a valid code from Fellowship Execs.")

        messages.warning(
            request, 
            "No UNbound account was found for this Google email. Please enter your Fellowship Invitation Code to activate your account."
        )
        raise ImmediateHttpResponse(redirect('register_code'))

    def save_user(self, request, sociallogin, form=None):
        """
        Runs when a new user registers.
        Marks the invitation code as used and sets up their Fellow profile.
        """
        user = super().save_user(request, sociallogin, form)

        invite_code_id = request.session.get('verified_invite_code_id')
        invite_obj = None
        if invite_code_id:
            try:
                invite_obj = InviteCode.objects.get(id=invite_code_id)
                invite_obj.mark_as_used(user)
                del request.session['verified_invite_code_id']
            except InviteCode.DoesNotExist:
                pass

        active_cohort = invite_obj.cohort if (invite_obj and invite_obj.cohort) else Cohort.objects.filter(is_active=True).first()
        role = invite_obj.role if invite_obj else 'fellow'

        Fellow.objects.get_or_create(
            user=user,
            defaults={
                'cohort': active_cohort,
                'role': role,
            }
        )
        return user