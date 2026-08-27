from functools import wraps
from django.http import HttpResponseForbidden
from django.contrib import messages
from django.shortcuts import redirect


def _get_role(user):
    if not user or not user.is_authenticated:
        return None
    if user.is_superuser:
        return 'system_admin'
    if hasattr(user, 'profile'):
        role = user.profile.role
        # Fallback: если профиль не judge, но есть активный judge
        if role != 'judge' and hasattr(user, 'judge') and user.judge.is_active:
            return 'judge'
        # Fallback: если профиль не fighter, но есть fighter
        if role != 'fighter' and hasattr(user, 'fighter'):
            return 'fighter'
        return role
    if hasattr(user, 'judge') and user.judge.is_active:
        return 'judge'
    if hasattr(user, 'fighter'):
        return 'fighter'
    return None


def system_admin_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('users:login')
        role = _get_role(request.user)
        if role == 'system_admin':
            return view_func(request, *args, **kwargs)
        return HttpResponseForbidden("Доступ запрещён. Требуются права системного администратора.")
    return _wrapped


def tournament_admin_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('users:login')
        role = _get_role(request.user)
        if role in ('system_admin', 'tournament_admin'):
            return view_func(request, *args, **kwargs)
        return HttpResponseForbidden("Доступ запрещён. Требуются права администратора.")
    return _wrapped


def tournament_admin_or_judge_required(view_func):
    """Доступ для администраторов турниров и судей"""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('users:login')
        role = _get_role(request.user)
        if role in ('system_admin', 'tournament_admin', 'judge'):
            return view_func(request, *args, **kwargs)
        return HttpResponseForbidden("Доступ запрещён. Требуются права администратора или судьи.")
    return _wrapped


def judge_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('users:login')
        if hasattr(request.user, 'judge') and request.user.judge.is_active:
            return view_func(request, *args, **kwargs)
        messages.error(request, 'У вас нет прав судьи')
        return redirect('home')
    return _wrapped


def fighter_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('users:login')
        role = _get_role(request.user)
        if role == 'fighter' or request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        return HttpResponseForbidden("Доступ запрещён. Требуются права участника.")
    return _wrapped