"""
Изоляция данных по федерациям.

Каждый пользователь видит только «свои» турниры:
  - superuser            → все
  - role='system_admin'  → все
  - role='tournament_admin' → только турниры своей федерации
  - остальные            → ничего
"""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from .models import Tournament

# Роли, которым разрешено создавать/редактировать турниры
ADMIN_ROLES = {'system_admin', 'tournament_admin'}


def get_user_tournaments(user):
    """
    Возвращает QuerySet турниров, доступных пользователю.
    Используется ВЕЗДЕ, где турнир достаётся по pk/id/slug.
    """
    if not user.is_authenticated:
        return Tournament.objects.none()

    if user.is_superuser:
        return Tournament.objects.all()

    # hasattr — на случай, если у пользователя не создан Profile
    profile = getattr(user, 'profile', None)
    if profile is None:
        return Tournament.objects.none()

    if profile.role == 'system_admin':
        return Tournament.objects.all()

    if profile.role == 'tournament_admin':
        if not profile.federation_id:
            # Админ без федерации — не видит ничего
            return Tournament.objects.none()
        return Tournament.objects.filter(federation=profile.federation)

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
    Заменяет @login_required там, где нужны админские права.
    """
    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not is_admin(request.user):
            raise PermissionDenied("Недостаточно прав для управления турнирами")
        return view_func(request, *args, **kwargs)

    return _wrapped