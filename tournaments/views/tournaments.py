import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Count
from users.decorators import tournament_admin_required
from ..models import Tournament, Fighter, Judge, AgeWeightCategory, Bracket, Fight
from ..forms import TournamentForm

logger = logging.getLogger('tournaments')


def tournament_list(request):
    """Список турниров"""
    queryset = Tournament.objects.annotate(
        reg_count=Count('registrations'),
        fight_count=Count('fights')
    ).order_by('-start_date')

    # Фильтры
    status = request.GET.get('status')
    search = request.GET.get('search')

    if status == 'active':
        queryset = queryset.filter(is_active=True)
    elif status == 'completed':
        queryset = queryset.filter(is_active=False)

    if search:
        queryset = queryset.filter(
            Q(name__icontains=search) | Q(location__icontains=search)
        )

    paginator = Paginator(queryset, 10)
    page = request.GET.get('page')
    tournaments = paginator.get_page(page)

    return render(request, 'tournaments/tournament_list.html', {
        'tournaments': tournaments,
        'status_filter': status or '',
        'search_query': search or '',
    })


def tournament_detail(request, pk):
    """Детальная информация о турнире"""
    tournament = get_object_or_404(
        Tournament.objects.annotate(
            reg_count=Count('registrations'),
            approved_count=Count('registrations', filter=Q(registrations__is_approved=True)),
            fight_count=Count('fights'),
            completed_count=Count('fights', filter=Q(fights__status='completed'))
        ),
        pk=pk
    )

    brackets = tournament.brackets.select_related('age_weight_category')
    categories = tournament.age_weight_categories.all()

    # Определяем, зарегистрирован ли текущий пользователь
    is_registered = False
    if request.user.is_authenticated and hasattr(request.user, 'fighter') and request.user.fighter:
        is_registered = request.user.fighter.registrations.filter(tournament=tournament).exists()

    context = {
        'tournament': tournament,
        'brackets': brackets,
        'categories': categories,
        'is_admin': _is_admin(request),
        'is_judge': _is_judge(request),
        'is_registered': is_registered,   # <-- добавлено
    }

    if request.user.is_authenticated and hasattr(request.user, 'judge') and request.user.judge.is_active:
        context['judge_fights'] = Fight.objects.filter(
            tournament=tournament, judge=request.user.judge
        ).select_related('fighter1', 'fighter2', 'winner')

    return render(request, 'tournaments/tournament_detail.html', context)


@login_required
@tournament_admin_required
def create_tournament(request):
    """Создание турнира"""
    if request.method == 'POST':
        form = TournamentForm(request.POST)
        if form.is_valid():
            tournament = form.save()
            messages.success(request, f'Турнир "{tournament.name}" создан')
            logger.info(f"Турнир #{tournament.id} создан пользователем {request.user}")
            return redirect('tournaments:tournament_detail', pk=tournament.pk)
        else:
            messages.error(request, 'Исправьте ошибки в форме')
    else:
        form = TournamentForm()

    return render(request, 'tournaments/create_tournament.html', {'form': form})


@login_required
@tournament_admin_required
def edit_tournament(request, pk):
    """Редактирование турнира"""
    tournament = get_object_or_404(Tournament, pk=pk)
    if request.method == 'POST':
        form = TournamentForm(request.POST, instance=tournament)
        if form.is_valid():
            form.save()
            messages.success(request, 'Турнир обновлён')
            return redirect('tournaments:tournament_detail', pk=pk)
    else:
        form = TournamentForm(instance=tournament)
    return render(request, 'tournaments/edit_tournament.html', {
        'form': form, 'tournament': tournament
    })


@login_required
@tournament_admin_required
def delete_tournament(request, pk):
    """Удаление турнира"""
    tournament = get_object_or_404(Tournament, pk=pk)
    if request.method == 'POST':
        name = tournament.name
        tournament.delete()
        messages.success(request, f'Турнир "{name}" удалён')
        logger.info(f"Турнир #{pk} удалён пользователем {request.user}")
        return redirect('tournaments:tournament_list')
    return render(request, 'tournaments/delete_tournament.html', {'tournament': tournament})


@login_required
def register_for_tournament(request, pk):
    """Регистрация на турнир"""
    tournament = get_object_or_404(Tournament, pk=pk)

    if not hasattr(request.user, 'fighter'):
        messages.error(request, 'У вас нет профиля бойца. Обратитесь к администратору.')
        return redirect('tournaments:tournament_detail', pk=pk)

    fighter = request.user.fighter

    if tournament.registrations.filter(fighter=fighter).exists():
        messages.warning(request, 'Вы уже зарегистрированы на этот турнир')
        return redirect('tournaments:my_registrations')

    from ..models import TournamentRegistration
    TournamentRegistration.objects.create(tournament=tournament, fighter=fighter)
    messages.success(request, f'Вы зарегистрированы на "{tournament.name}"')
    return redirect('tournaments:my_registrations')


@login_required
def my_registrations(request):
    """Мои регистрации"""
    if not hasattr(request.user, 'fighter'):
        messages.error(request, 'Профиль бойца не найден')
        return redirect('home')

    registrations = request.user.fighter.registrations.select_related(
        'tournament', 'age_weight_category'
    ).order_by('-tournament__start_date')

    return render(request, 'tournaments/my_registrations.html', {
        'registrations': registrations,
        'fighter': request.user.fighter,
    })


@login_required
def my_tournaments(request):
    """Мои турниры (для бойца)"""
    if not hasattr(request.user, 'fighter'):
        messages.error(request, 'Профиль бойца не найден')
        return redirect('home')

    registrations = request.user.fighter.registrations.select_related(
        'tournament', 'age_weight_category'
    ).order_by('-tournament__start_date')

    active = [r for r in registrations if r.tournament.is_active]
    completed = [r for r in registrations if not r.tournament.is_active]

    return render(request, 'tournaments/my_tournaments.html', {
        'active': active,
        'completed': completed,
    })


# Helpers

def _is_admin(request):
    if not request.user.is_authenticated:
        return False
    return request.user.is_superuser or (
        hasattr(request.user, 'profile') and
        request.user.profile.role in ('system_admin', 'tournament_admin')
    )


def _is_judge(request):
    if not request.user.is_authenticated:
        return False
    return hasattr(request.user, 'judge') and request.user.judge.is_active