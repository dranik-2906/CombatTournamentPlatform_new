import logging
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.utils import timezone
from tournaments.models import Tournament, Fighter, Judge, Fight
from users.decorators import get_user_role

logger = logging.getLogger('users')


def home(request):
    """Главная страница"""
    now = timezone.now().date()

    # Статистика
    stats = {
        'total_tournaments': Tournament.objects.count(),
        'active_tournaments': Tournament.objects.filter(is_active=True, end_date__gte=now).count(),
        'total_fighters': Fighter.objects.count(),
        'active_judges': Judge.objects.filter(is_active=True).count(),
        'total_fights': Fight.objects.count(),
        'completed_fights': Fight.objects.filter(status='completed').count(),
    }

    # Ближайшие турниры
    upcoming = Tournament.objects.filter(
        is_active=True, start_date__gte=now
    ).order_by('start_date')[:5]

    # Текущие турниры
    current = Tournament.objects.filter(
        is_active=True, start_date__lte=now, end_date__gte=now
    ).order_by('start_date')[:5]

    context = {
        'stats': stats,
        'upcoming_tournaments': upcoming,
        'current_tournaments': current,
    }
    return render(request, 'home.html', context)

from users.roles import (
    get_user_role, is_tournament_admin, is_judge, is_coach, is_fighter,
)

@login_required
def dashboard(request):
    user = request.user
    now = timezone.now().date()
    context = {
        'role': get_user_role(user),  # только для бейджа в шаблоне
        'tournaments': Tournament.objects.filter(
            is_active=True, end_date__gte=now
        ).order_by('start_date'),
    }

    if is_tournament_admin(user):
        context.update({ ...как раньше для админов... })

    if is_judge(user):
        judge = getattr(user, 'judge', None)
        if judge:
            context.update({ ...панель судьи... })

    if is_coach(user):
        coach = getattr(user, 'coach', None)
        if coach:
            context.update({
                'coach': coach,
                'my_students': coach.students.select_related('user'),
                'students_fights': Fight.objects.filter(
                    Q(fighter1__in=coach.students.all())
                    | Q(fighter2__in=coach.students.all())
                ).select_related('tournament').order_by('-updated_at')[:10],
            })
    # Боец
    if is_fighter(user):
        fighter = getattr(user, 'fighter', None)
        if fighter:
            context.update({
                'fighter': fighter,
                'my_registrations': fighter.registrations.select_related('tournament').order_by('-created_at')[:10],
                'my_stats': fighter.get_stats(),
            })
    return render(request, 'core/dashboard.html', context)


def _detect_role(user):
    """
    Определение роли пользователя.
    Приоритет: Судья > Системный админ > Организатор > Боец > Гость
    """
    # --- СУДЬЯ (проверяем оба источника: profile.role и модель Judge) ---
    is_judge = False
    if hasattr(user, 'profile') and user.profile:
        if user.profile.role == 'judge':
            is_judge = True

    if not is_judge and hasattr(user, 'judge'):
        try:
            if user.judge and user.judge.is_active:
                is_judge = True
        except Exception:
            pass

    if is_judge:
        return 'judge'

    # --- СИСТЕМНЫЙ АДМИНИСТРАТОР ---
    if user.is_superuser:
        return 'system_admin'

    # --- РОЛИ ИЗ ПРОФИЛЯ ---
    if hasattr(user, 'profile') and user.profile:
        profile_role = user.profile.role
        if profile_role == 'system_admin':
            return 'system_admin'
        if profile_role == 'tournament_admin':
            return 'tournament_admin'
        if profile_role == 'fighter':
            return 'fighter'

    # --- FALLBACK ПО МОДЕЛЯМ ---
    if hasattr(user, 'fighter'):
        return 'fighter'

    return 'guest'