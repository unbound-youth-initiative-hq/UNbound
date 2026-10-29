"""Safe recovery from an expired form without weakening CSRF protection."""
from django.http import JsonResponse
from django.shortcuts import render


def csrf_failure(request, reason=''):
    message = 'This form expired or your session changed. Reopen the page and try again.'
    if request.content_type == 'application/json':
        return JsonResponse({'detail': message}, status=403)
    target = request.path if request.path.startswith('/admin/') else '/accounts/register/' if request.path.startswith('/accounts/register/') else '/dashboard/'
    return render(request, 'session_expired.html', {'recovery_url': target}, status=403)
