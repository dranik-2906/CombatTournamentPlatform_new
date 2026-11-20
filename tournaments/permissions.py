"""
Изоляция данных по федерациям.
"""
from functools import wraps
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from .models import Tournament

# Роли, которым разрешено создавать/редактировать турниры
ADMIN_ROLES = {'system_admin', 'tournament_admin'}


def get_visible_tournaments(user):
    """
    Какие турниры пользователь может ВИДЕТЬ.
    """
    if not user.is_authenticated:
        return Tournament.objects.none()

    # Суперюзер видит всё
    if user.is_superuser:
        return Tournament.objects.all()

    profile = getattr(user, 'profile', None)
    if profile is None:
        return Tournament.objects.none()

    # Системный админ видит всё
    if profile.role == 'system_admin':
        return Tournament.objects.all()

    # Создаем пустой Q-объект для объединения условий
    q = Q()

    # Если пользователь - админ турнира
    if profile.role == 'tournament_admin':
        if profile.federation_id:
            q |= Q(federation=profile.federation)
        else:
            q |= Q(federation__isnull=True)

    # Если у пользователя есть федерация (для бойцов, судей, тренеров)
    if profile.federation_id:
        q |= Q(federation=profile.federation)

    # Если ни одно условие не добавилось — ничего не показываем
    if not q:
        return Tournament.objects.none()

    # Возвращаем турниры, подходящие хотя бы под одно условие
    return Tournament.objects.filter(q).distinct()


def get_managed_tournaments(user):
    """
    Какими турнирами пользователь может УПРАВЛЯТЬ.
    """
    if not user.is_authenticated:
        return Tournament.objects.none()

    if user.is_superuser:
        return Tournament.objects.all()

    profile = getattr(user, 'profile', None)
    if profile is None:
        return Tournament.objects.none()

    if profile.role == 'system_admin':
        return Tournament.objects.all()

    if profile.role == 'tournament_admin':
        if profile.federation_id:
            return Tournament.objects.filter(federation=profile.federation)
        else:
            return Tournament.objects.filter(federation__isnull=True)

    return Tournament.objects.none()


def is_admin(user):
    """Может ли пользователь создавать/редактировать турниры (по роли)."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    profile = getattr(user, 'profile', None)
    return bool(profile and profile.role in ADMIN_ROLES)


def admin_required(view_func):
    """
    Декоратор: login + проверка роли.
    """
    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not is_admin(request.user):
            raise PermissionDenied("Недостаточно прав для управления турнирами")
        return view_func(request, *args, **kwargs)

    return _wrapped