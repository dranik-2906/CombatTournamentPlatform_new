from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect


def get_user_role(user):
    """Единая функция определения роли пользователя."""
    if not user or not user.is_authenticated:
        return 'guest'
    if user.is_superuser:
        return 'system_admin'

    profile = getattr(user, 'profile', None)
    if profile and profile.role in ('system_admin', 'tournament_admin'):
        return profile.role

    if hasattr(user, 'judge') and user.judge.is_active:
        return 'judge'
    if hasattr(user, 'fighter'):
        return 'fighter'
    if profile:
        return profile.role
    return 'guest'


def role_required(*allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('users:login')
            if get_user_role(request.user) in allowed_roles:
                return view_func(request, *args, **kwargs)
            messages.error(request, 'У вас недостаточно прав для этого действия')
            return redirect('home')
        return _wrapped
    return decorator


def judge_required(view_func):
    """
    Проверяет фактическое наличие активного Judge.
    Если роль судьи есть, но профиля нет — выводит понятную ошибку.
    """

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('users:login')
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)

        # 1. Если есть связанный Judge и он активен
        if hasattr(request.user, 'judge') and request.user.judge.is_active:
            return view_func(request, *args, **kwargs)

        # 2. Если роль судьи есть, но объекта Judge нет
        if getattr(request.user, 'profile', None) and request.user.profile.role == 'judge':
            messages.error(
                request,
                'Ваш аккаунт имеет роль судьи, но не привязан к судейскому профилю. '
                'Обратитесь к администратору для завершения настройки.'
            )
            return redirect('home')

        # 3. Во всех остальных случаях
        messages.error(request, 'У вас нет прав судьи')
        return redirect('home')

    return _wrapped


def fighter_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('users:login')
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        if hasattr(request.user, 'fighter'):
            return view_func(request, *args, **kwargs)
        messages.error(request, 'У вас нет прав участника')
        return redirect('home')
    return _wrapped


def tournament_admin_required(view_func):
    return role_required('system_admin', 'tournament_admin')(view_func)


def system_admin_required(view_func):
    return role_required('system_admin')(view_func)


def tournament_admin_or_judge_required(view_func):
    """
    Доступ для администратора турнира, системного администратора
    или активного судьи.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('users:login')
        role = get_user_role(request.user)
        if role in ('system_admin', 'tournament_admin'):
            return view_func(request, *args, **kwargs)
        if hasattr(request.user, 'judge') and request.user.judge.is_active:
            return view_func(request, *args, **kwargs)
        messages.error(request, 'У вас недостаточно прав для этого действия')
        return redirect('home')
    return _wrapped


def tournament_admin_or_fighter_required(view_func):
    """
    Доступ для администратора турнира или участника.
    Используется в местах, где нужен либо тот, либо другой.
    """
    return role_required('system_admin', 'tournament_admin', 'fighter')(view_func)


def any_role_required(view_func):
    """Просто требует авторизации (для полноты)."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('users:login')
        return view_func(request, *args, **kwargs)
    return _wrapped