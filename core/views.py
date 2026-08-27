import logging
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.utils import timezone
from tournaments.models import Tournament, Fighter, Judge, Fight

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


@login_required
def dashboard(request):
    """Панель управления / Личный кабинет"""
    user = request.user
    role = _detect_role(user)
    now = timezone.now().date()

    context = {
        'user': user,
        'role': role,
        'tournaments': Tournament.objects.filter(is_active=True, end_date__gte=now).order_by('start_date'),
    }

    # Администратор / Организатор
    if role in ('system_admin', 'tournament_admin'):
        context.update({
            'fighters_count': Fighter.objects.count(),
            'judges_count': Judge.objects.filter(is_active=True).count(),
            'total_tournaments': Tournament.objects.count(),
            'pending_approvals': Fighter.objects.filter(
                registrations__is_approved=False
            ).count(),
        })

    # Судья
    elif role == 'judge':
        judge = getattr(user, 'judge', None)
        if judge:
            fights = Fight.objects.filter(judge=judge)
            context.update({
                'judge': judge,
                'active_fights': fights.filter(status='in_progress').count(),
                'upcoming_fights': fights.filter(status='scheduled').count(),
                'completed_fights': fights.filter(status='completed').count(),
                'recent_fights': fights.order_by('-updated_at')[:10],
            })

    # Боец
    elif role == 'fighter':
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