import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.db.models import Count
from users.decorators import tournament_admin_required
from ..models import Tournament, Bracket, AgeWeightCategory, Fight, TournamentRegistration
from ..services import BracketService, FightService
from ..forms import AgeWeightCategoryForm

logger = logging.getLogger('tournaments')


@login_required
def bracket_view(request, tournament_id, bracket_id):
    """Просмотр турнирной сетки"""
    tournament = get_object_or_404(Tournament, pk=tournament_id)
    bracket = get_object_or_404(Bracket, pk=bracket_id, tournament=tournament)

    # === ОБРАБОТКА ГАЛОЧКИ "БОЙ ЗА 3-Е МЕСТО" ===
    if request.method == 'POST' and (_is_admin(request) or request.user.is_superuser):
        has_bronze = request.POST.get('has_bronze_match') == 'on'
        bracket.has_bronze_match = has_bronze
        bracket.save()

        if has_bronze:
            bronze_exists = Fight.objects.filter(bracket=bracket, is_bronze_match=True).exists()
            if not bronze_exists:
                semi_round = bracket.total_rounds - 1
                semi_finals = Fight.objects.filter(bracket=bracket, round_number=semi_round, status='completed',
                                                   is_bronze_match=False)
                losers = []
                for sf in semi_finals:
                    if sf.fighter1 and sf.fighter2:
                        loser = sf.fighter2 if sf.winner == sf.fighter1 else sf.fighter1
                        losers.append(loser)

                if len(losers) == 2:
                    from ..services import BracketService
                    fight_defaults = BracketService._get_fight_defaults(bracket) if hasattr(BracketService,
                                                                                            '_get_fight_defaults') else {}
                    Fight.objects.create(
                        tournament=bracket.tournament,
                        bracket=bracket,
                        age_weight_category=bracket.age_weight_category,
                        round_number=bracket.total_rounds,
                        match_number=99,
                        status='scheduled',
                        is_bronze_match=True,
                        fighter1=losers[0],
                        fighter2=losers[1],
                        **fight_defaults
                    )
        else:
            Fight.objects.filter(bracket=bracket, is_bronze_match=True, status='scheduled').delete()

        messages.success(request, 'Настройки боя за 3-е место обновлены')
        return redirect('tournaments:bracket_view', tournament_id=tournament.id, bracket_id=bracket.id)

    # === ОСНОВНАЯ ЛОГИКА ===
    fights_by_round = FightService.get_fights_by_round(bracket)
    all_fights = bracket.fights.all().select_related('fighter1', 'fighter2', 'winner').order_by('round_number',
                                                                                                'match_number')

    # Авто-завершение сетки если все бои завершены
    if all_fights.exists() and not all_fights.exclude(status='completed').exists():
        if bracket.status != 'completed':
            bracket.status = 'completed'
            bracket.save()
            messages.success(request, f'Сетка "{bracket.name}" автоматически завершена!')

    # === ПОЛУЧЕНИЕ СТЕНДИНГОВ (ТАБЛИЦЫ ЛИДЕРОВ) ===
    standings_a, standings_b = [], []

    if bracket.bracket_type == 'mixed':
        # Локальная функция для расчета очков внутри одной группы
        def get_group_standings(group_name):
            group_fights = bracket.fights.filter(group_name=group_name)
            stats = {}

            # Инициализируем всех участников группы
            for f in group_fights:
                if f.fighter1 and f.fighter1.id not in stats:
                    stats[f.fighter1.id] = {'fighter': f.fighter1, 'wins': 0, 'draws': 0, 'losses': 0, 'points': 0,
                                            'score_diff': 0, 'place': None}
                if f.fighter2 and f.fighter2.id not in stats:
                    stats[f.fighter2.id] = {'fighter': f.fighter2, 'wins': 0, 'draws': 0, 'losses': 0, 'points': 0,
                                            'score_diff': 0, 'place': None}

            # Считаем очки по завершенным боям
            for f in group_fights.filter(status='completed'):
                if not f.fighter1 or not f.fighter2: continue
                s1 = stats[f.fighter1.id]
                s2 = stats[f.fighter2.id]

                s1['score_diff'] += (f.score_fighter1 - f.score_fighter2)
                s2['score_diff'] += (f.score_fighter2 - f.score_fighter1)

                if f.is_draw:
                    s1['draws'] += 1;
                    s1['points'] += 1
                    s2['draws'] += 1;
                    s2['points'] += 1
                elif f.winner_id == f.fighter1_id:
                    s1['wins'] += 1;
                    s1['points'] += 3
                    s2['losses'] += 1
                elif f.winner_id == f.fighter2_id:
                    s2['wins'] += 1;
                    s2['points'] += 3
                    s1['losses'] += 1

            sorted_stats = sorted(stats.values(), key=lambda x: (x['points'], x['score_diff'], x['wins']), reverse=True)
            for idx, s in enumerate(sorted_stats):
                s['place'] = idx + 1
            return sorted_stats

        standings_a = get_group_standings('A')
        standings_b = get_group_standings('B')
        standings = standings_a + standings_b
    else:
        standings = FightService.get_standings(bracket) if all_fights.exists() else []

    place_map = {s['fighter'].id: s['place'] for s in standings if s.get('place')} if standings else {}

    # --- ЛОГИКА ОПРЕДЕЛЕНИЯ ПРИЗЁРОВ (1, 2, 3, 4 места) ---
    prizes = []

    # 1. Для Олимпийской и Смешанной (плей-офф)
    if bracket.bracket_type in ('single_elimination', 'mixed'):
        final_fight = Fight.objects.filter(bracket=bracket, round_number=bracket.total_rounds,
                                           is_bronze_match=False).first()

        if final_fight and final_fight.status == 'completed' and final_fight.winner:
            # 1-е место
            prizes.append(
                {'place': 1, 'fighter': final_fight.winner, 'note': final_fight.get_win_method_display() or 'Финал',
                 'is_bronze_winner': False})

            # 2-е место
            loser_final = final_fight.fighter2 if final_fight.winner == final_fight.fighter1 else final_fight.fighter1
            if loser_final:
                prizes.append({'place': 2, 'fighter': loser_final, 'note': 'Финал', 'is_bronze_winner': False})

            # 3 и 4 места
            if getattr(bracket, 'has_bronze_match', False):
                bronze_fight = Fight.objects.filter(bracket=bracket, is_bronze_match=True).first()
                if bronze_fight and bronze_fight.status == 'completed' and bronze_fight.winner:
                    prizes.append({'place': 3, 'fighter': bronze_fight.winner, 'note': 'Бой за 3-е место',
                                   'is_bronze_winner': True})
                    loser_bronze = bronze_fight.fighter2 if bronze_fight.winner == bronze_fight.fighter1 else bronze_fight.fighter1
                    if loser_bronze:
                        prizes.append({'place': 4, 'fighter': loser_bronze, 'note': 'Бой за 3-е место',
                                       'is_bronze_winner': False})
                else:
                    prizes.append(
                        {'place': 3, 'fighter': None, 'note': 'Ожидает боя за 3-е место', 'is_bronze_winner': False})
            else:
                semi_round = bracket.total_rounds - 1
                semi_finals = Fight.objects.filter(bracket=bracket, round_number=semi_round, status='completed',
                                                   is_bronze_match=False)
                for sf in semi_finals:
                    if sf.fighter1 and sf.fighter2:
                        loser = sf.fighter2 if sf.winner == sf.fighter1 else sf.fighter1
                        prizes.append({'place': 3, 'fighter': loser, 'note': 'Полуфиналист', 'is_bronze_winner': False})

        # Если финала еще нет (идет групповой этап), показываем текущих лидеров
        elif bracket.bracket_type == 'mixed' and standings:
            all_sorted = sorted(standings, key=lambda x: (x.get('points', 0), x.get('score_diff', 0)), reverse=True)
            for idx, s in enumerate(all_sorted[:3]):
                prizes.append(
                    {'place': idx + 1, 'fighter': s['fighter'], 'note': 'Лидер группы', 'is_bronze_winner': False})

    # 2. Для Круговой системы (призеры берутся из общей таблицы)
    elif bracket.bracket_type == 'round_robin' and standings:
        for s in standings[:3]:
            if s.get('place') and s['place'] <= 3:
                wins_count = s.get('wins', 0)
                prizes.append({'place': s['place'], 'fighter': s['fighter'], 'note': f"{wins_count} побед",
                               'is_bronze_winner': False})

    # --- СБОР УЧАСТНИКОВ ДЛЯ ТАБЛИЦЫ ---
    participants = []
    participants_a, participants_b = [], []

    if bracket.bracket_type in ('round_robin', 'mixed'):
        seen = set()
        seen_a, seen_b = set(), set()

        for fight in all_fights:
            if bracket.bracket_type == 'mixed':
                if fight.group_name == 'A':
                    for f in (fight.fighter1, fight.fighter2):
                        if f and f.id not in seen_a:
                            seen_a.add(f.id)
                            participants_a.append(f)
                elif fight.group_name == 'B':
                    for f in (fight.fighter1, fight.fighter2):
                        if f and f.id not in seen_b:
                            seen_b.add(f.id)
                            participants_b.append(f)

            for f in (fight.fighter1, fight.fighter2):
                if f and f.id not in seen:
                    seen.add(f.id)
                    participants.append(f)

    context = {
        'tournament': tournament,
        'bracket': bracket,
        'fights_by_round': fights_by_round,
        'all_fights': all_fights,
        'standings': standings,
        'standings_a': standings_a,
        'standings_b': standings_b,
        'place_map': place_map,
        'prizes': prizes,
        'participants': participants,
        'participants_a': participants_a,
        'participants_b': participants_b,
        'max_round': max(fights_by_round.keys()) if fights_by_round else 0,
        'is_admin': _is_admin(request),
        'is_judge': _is_judge(request),
    }

    if _is_judge(request):
        context['judge_fight'] = Fight.objects.filter(bracket=bracket, judge=request.user.judge).first()

    return render(request, 'tournaments/bracket_view.html', context)

@login_required
@tournament_admin_required
def generate_brackets(request, tournament_id):
    """Генерация сеток для всех категорий"""
    tournament = get_object_or_404(Tournament, pk=tournament_id)
    categories = AgeWeightCategory.objects.filter(tournament=tournament)

    if not categories.exists():
        messages.error(request, 'Сначала создайте возрастно-весовые категории')
        return redirect('tournaments:manage_categories', tournament_id=tournament_id)

    registrations = TournamentRegistration.objects.filter(
        tournament=tournament, is_approved=True, age_weight_category__isnull=False
    ).select_related('fighter', 'age_weight_category')

    if not registrations.exists():
        messages.error(request, 'Нет допущенных участников с назначенными категориями')
        return redirect('tournaments:participants_management')

    created = 0
    for category in categories:
        cat_regs = [r for r in registrations if r.age_weight_category_id == category.id]

        if len(cat_regs) < 2:
            messages.info(request, f'Категория "{category.name}": недостаточно участников')
            continue

        if Bracket.objects.filter(tournament=tournament, age_weight_category=category, is_generated=True).exists():
            messages.info(request, f'Категория "{category.name}": сетка уже существует')
            continue

        bracket, _ = Bracket.objects.get_or_create(
            tournament=tournament,
            age_weight_category=category,
            defaults={
                'bracket_type': category.bracket_system,
                'is_generated': False,
                'name': f"{category.name} ({category.get_gender_display()})"
            }
        )

        if category.bracket_system == 'round_robin':
            # Извлекаем самих бойцов из регистраций
            participants = [reg.fighter for reg in cat_regs]
            success, msg = BracketService.generate_round_robin(bracket, participants)
        elif category.bracket_system == 'mixed':
            success, msg = BracketService.generate_mixed(bracket, cat_regs)
        else:
            participants = [reg.fighter for reg in cat_regs]
            success, msg = BracketService.generate_single_elimination(bracket, participants)

        if success:
            created += 1
            messages.success(request, f'✅ {category.name}: {msg}')
        else:
            messages.error(request, f'❌ {category.name}: {msg}')

    if created > 0:
        messages.success(request, f'Создано {created} сеток')
    return redirect('tournaments:tournament_detail', pk=tournament_id)


@login_required
@tournament_admin_required
def advance_winners_view(request, tournament_id):
    """Продвижение победителей для конкретной сетки (или всех)"""
    tournament = get_object_or_404(Tournament, pk=tournament_id)

    # Если передан bracket_id — продвигаем только его
    bracket_id = request.GET.get('bracket_id') or request.POST.get('bracket_id')
    if bracket_id:
        bracket = get_object_or_404(Bracket, pk=bracket_id, tournament=tournament)
        success, msg = BracketService.advance_winners(bracket)
        if success:
            messages.success(request, f'{bracket.name}: {msg}')
        else:
            messages.error(request, f'{bracket.name}: {msg}')
        return redirect('tournaments:bracket_view', tournament_id=tournament_id, bracket_id=bracket.id)

    # Иначе продвигаем все активные сетки
    brackets = Bracket.objects.filter(tournament=tournament, status__in=['generated', 'in_progress'])
    advanced = 0
    for bracket in brackets:
        success, msg = BracketService.advance_winners(bracket)
        if success:
            advanced += 1
            messages.success(request, f'{bracket.name}: {msg}')
        else:
            messages.info(request, f'{bracket.name}: {msg}')

    if advanced == 0:
        messages.info(request, 'Нет сеток для продвижения')
    return redirect('tournaments:tournament_detail', pk=tournament_id)


@login_required
@tournament_admin_required
def delete_bracket(request, tournament_id, bracket_id):
    """Удаление сетки"""
    bracket = get_object_or_404(Bracket, pk=bracket_id, tournament_id=tournament_id)
    bracket.delete()
    messages.success(request, 'Сетка удалена')
    return redirect('tournaments:tournament_detail', pk=tournament_id)


@login_required
@tournament_admin_required
def manage_categories(request, tournament_id):
    """Управление категориями турнира"""
    tournament = get_object_or_404(Tournament, pk=tournament_id)

    categories = tournament.age_weight_categories.prefetch_related('registrations')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create':
            form = AgeWeightCategoryForm(request.POST)
            if form.is_valid():
                cat = form.save(commit=False)
                cat.tournament = tournament
                cat.save()
                messages.success(request, f'Категория "{cat.name}" создана')
            else:
                messages.error(request, 'Ошибки в форме')

        elif action == 'edit':
            cat_id = request.POST.get('category_id')
            category = get_object_or_404(AgeWeightCategory, pk=cat_id, tournament=tournament)
            form = AgeWeightCategoryForm(request.POST, instance=category)
            if form.is_valid():
                form.save()
                messages.success(request, 'Категория обновлена')

        elif action == 'delete':
            cat_id = request.POST.get('category_id')
            category = get_object_or_404(AgeWeightCategory, pk=cat_id, tournament=tournament)
            name = category.name
            category.delete()
            messages.success(request, f'Категория "{name}" удалена')

        return redirect('tournaments:manage_categories', tournament_id=tournament_id)

    form = AgeWeightCategoryForm()
    return render(request, 'tournaments/manage_categories.html', {
        'tournament': tournament,
        'categories': categories,
        'form': form,
    })


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