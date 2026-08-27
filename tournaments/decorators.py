from functools import wraps
from django.http import HttpResponseForbidden
from django.contrib import messages
from django.shortcuts import redirect


def admin_required(view_func):
    """Декоратор для проверки прав администратора"""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('users:login')
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        if hasattr(request.user, 'profile') and request.user.profile.role in ('system_admin', 'tournament_admin'):
            return view_func(request, *args, **kwargs)
        messages.error(request, 'У вас нет прав администратора')
        return HttpResponseForbidden('Доступ запрещён')
    return _wrapped
