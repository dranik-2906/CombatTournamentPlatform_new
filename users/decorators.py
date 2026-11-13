from functools import wraps
from django.contrib import messages
from django.shortcuts import redirect
from .roles import (
    get_user_roles, is_judge, is_coach, is_fighter,
    is_tournament_admin, is_system_admin,
)


def role_required(*allowed_roles):
    """Доступ, если у пользователя есть ХОТЯ БЫ ОДНА из ролей."""

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('users:login')
            if get_user_roles(request.user) & set(allowed_roles):
                return view_func(request, *args, **kwargs)
            messages.error(request, 'У вас недостаточно прав для этого действия')
            return redirect('home')

        return _wrapped

    return decorator


def system_admin_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('users:login')
        if is_system_admin(request.user):
            return view_func(request, *args, **kwargs)
        messages.error(request, 'Нужны права администратора системы')
        return redirect('home')

    return _wrapped


def tournament_admin_required(view_func):
    return role_required('system_admin', 'tournament_admin')(view_func)


def judge_required(view_func):
    """Панель судьи: нужен активный объект Judge (суперюзер — тоже ок)."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('users:login')
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        if is_judge(request.user):
            return view_func(request, *args, **kwargs)
        profile = getattr(request.user, 'profile', None)
        if profile and profile.role == 'judge':
            messages.error(
                request,
                'Ваш аккаунт имеет роль судьи, но не привязан к судейскому профилю. '
                'Обратитесь к администратору.'
            )
            return redirect('home')
        messages.error(request, 'У вас нет прав судьи')
        return redirect('home')

    return _wrapped


def coach_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('users:login')
        if is_coach(request.user) or request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        messages.error(request, 'Раздел доступен только тренерам')
        return redirect('home')

    return _wrapped


def fighter_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('users:login')
        if is_fighter(request.user) or request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        messages.error(request, 'У вас нет прав участника')
        return redirect('home')

    return _wrapped


# === ДОБАВЛЕННЫЙ ДЕКОРАТОР ===
def tournament_admin_or_judge_required(view_func):
    """
    Доступ для администратора турнира, системного администратора
    или активного судьи.
    """

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('users:login')

        # Админы проходят всегда
        if is_system_admin(request.user) or is_tournament_admin(request.user):
            return view_func(request, *args, **kwargs)

        # Судьи проходят, если они активны
        if is_judge(request.user):
            return view_func(request, *args, **kwargs)

        # Суперпользователь
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)

        messages.error(request, 'У вас недостаточно прав для этого действия')
        return redirect('home')

    return _wrapped