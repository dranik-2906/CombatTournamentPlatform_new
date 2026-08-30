import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.utils import timezone
from users.decorators import (
    tournament_admin_required, tournament_admin_or_judge_required, judge_required
)
from ..models import Tournament, Fight, Judge, AgeWeightCategory, TimerSettings, Fighter, RoundScore
from ..services import FightService
from ..forms import FightResultForm, AssignJudgeForm, TimerSettingsForm

logger = logging.getLogger('tournaments')


# ==================== ADMIN / MANAGEMENT ====================

@login_required
@tournament_admin_or_judge_required
def fights_management(request, tournament_id):
    """Управление боями турнира (админ) / просмотр своих боёв (судья)"""
    tournament = get_object_or_404(Tournament, pk=tournament_id)
    fights = Fight.objects.filter(tournament=tournament).select_related(
        'fighter1', 'fighter2', 'winner', 'judge', 'age_weight_category', 'head_judge'
    ).order_by('round_number', 'match_number')

    is_judge = hasattr(request.user, 'judge') and request.user.judge.is_active
    is_admin = (
        request.user.is_superuser or
        (hasattr(request.user, 'profile') and request.user.profile.role in ('system_admin', 'tournament_admin'))
    )

    if is_judge and not is_admin:
        # Бокс: показываем бои, где пользователь — любой из судей
        if tournament.is_boxing:
            from django.db.models import Q
            fights = fights.filter(
                Q(head_judge=request.user.judge) |
                Q(side_judges=request.user.judge)
            ).distinct()
        else:
            fights = fights.filter(judge=request.user.judge)

    status_filter = request.GET.get('status')
    category_filter = request.GET.get('category')
    judge_filter = request.GET.get('judge')

    if status_filter:
        fights = fights.filter(status=status_filter)
    if category_filter:
        fights = fights.filter(age_weight_category_id=category_filter)
    if judge_filter and is_admin:
        fights = fights.filter(judge_id=judge_filter)

    paginator = Paginator(fights, 20)
    page = request.GET.get('page')
    fights_page = paginator.get_page(page)

    context = {
        'tournament': tournament,
        'fights': fights_page,
        'total': fights.count(),
        'scheduled': fights.filter(status='scheduled').count(),
        'in_progress': fights.filter(status='in_progress').count(),
        'completed': fights.filter(status='completed').count(),
        'no_judge': fights.filter(judge__isnull=True, head_judge__isnull=True).count() if is_admin else 0,
        'judges': Judge.objects.filter(is_active=True) if is_admin else Judge.objects.none(),
        'categories': AgeWeightCategory.objects.filter(tournament=tournament),
        'status_filter': status_filter or '',
        'is_admin': is_admin,
        'is_judge_view': is_judge and not is_admin,
    }
    return render(request, 'tournaments/fights_management.html', context)


@login_required
@tournament_admin_required
def assign_judge(request, tournament_id, fight_id):
    """Назначить судью на бой (для видов спорта с одним судьёй)"""
    tournament = get_object_or_404(Tournament, pk=tournament_id)
    fight = get_object_or_404(Fight, pk=fight_id, tournament=tournament)

    # Если бокс/MMA/кикбоксинг — редирект на назначение боксёрских судей
    if tournament.sport_type in ('boxing', 'mma', 'kickboxing'):
        return redirect('tournaments:assign_boxing_judges', tournament_id=tournament_id, fight_id=fight_id)

    if request.method == 'POST':
        form = AssignJudgeForm(request.POST)
        if form.is_valid():
            judge = form.cleaned_data['judge']
            assign_to_cat = form.cleaned_data['assign_to_category']
            success, msg = FightService.assign_judge(fight, judge, assign_to_cat)
            if success:
                messages.success(request, msg)
            else:
                messages.error(request, msg)
        return redirect('tournaments:fights_management', tournament_id=tournament_id)

    form = AssignJudgeForm()
    return render(request, 'tournaments/assign_judge.html', {
        'form': form, 'tournament': tournament, 'fight': fight
    })


@login_required
@tournament_admin_required
def assign_boxing_judges(request, tournament_id, fight_id):
    """Назначить главного и боковых судей на бой (для бокса/MMA/кикбоксинга)"""
    tournament = get_object_or_404(Tournament, pk=tournament_id)
    fight = get_object_or_404(Fight, pk=fight_id, tournament=tournament)

    # Если не бокс/MMA/кикбоксинг — редирект на обычное назначение
    if tournament.sport_type not in ('boxing', 'mma', 'kickboxing'):
        messages.error(request, 'Назначение боковых судей доступно только для бокса, MMA и кикбоксинга')
        return redirect('tournaments:assign_judge', tournament_id=tournament_id, fight_id=fight_id)

    side_count = fight.age_weight_category.side_judges_count if fight.age_weight_category else 3

    if request.method == 'POST':
        head_judge_id = request.POST.get('head_judge')
        side_judge_ids = request.POST.getlist('side_judges')

        if not head_judge_id:
            messages.error(request, 'Главный судья обязателен')
            return redirect('tournaments:assign_boxing_judges', tournament_id=tournament_id, fight_id=fight_id)

        if len(side_judge_ids) != side_count:
            messages.error(request, f'Необходимо выбрать ровно {side_count} боковых судей')
            return redirect('tournaments:assign_boxing_judges', tournament_id=tournament_id, fight_id=fight_id)

        head_judge = get_object_or_404(Judge, pk=head_judge_id, is_active=True)
        side_judges = Judge.objects.filter(id__in=side_judge_ids, is_active=True)

        success, msg = FightService.assign_boxing_judges(fight, head_judge, list(side_judges))
        if success:
            messages.success(request, msg)
        else:
            messages.error(request, msg)
        return redirect('tournaments:fights_management', tournament_id=tournament_id)

    head_judges = Judge.objects.filter(is_active=True)
    side_judges = Judge.objects.filter(is_active=True)
    if fight.head_judge:
        side_judges = side_judges.exclude(pk=fight.head_judge.pk)

    context = {
        'tournament': tournament,
        'fight': fight,
        'head_judges': head_judges,
        'side_judges': side_judges,
        'side_count': side_count,
        'selected_head': fight.head_judge_id,
        'selected_side': list(fight.side_judges.values_list('id', flat=True)),
    }
    return render(request, 'tournaments/assign_boxing_judges.html', context)
@login_required
@tournament_admin_required
def admin_update_fight(request, tournament_id, fight_id):
    """Обновление статуса боя админом"""
    tournament = get_object_or_404(Tournament, pk=tournament_id)
    fight = get_object_or_404(Fight, pk=fight_id, tournament=tournament)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'start':
            success, msg = FightService.start_fight(fight)
        elif action == 'complete':
            form = FightResultForm(request.POST, instance=fight, fight=fight)
            if form.is_valid():
                winner = form.cleaned_data.get('winner')
                success, msg = FightService.complete_fight(
                    fight, winner=winner,
                    method=form.cleaned_data.get('win_method', ''),
                    notes=form.cleaned_data.get('judge_notes', ''),
                    scores={
                        'fighter1': form.cleaned_data.get('score_fighter1', 0),
                        'fighter2': form.cleaned_data.get('score_fighter2', 0),
                    }
                )
            else:
                messages.error(request, 'Ошибки в форме результата')
                return redirect('tournaments:fights_management', tournament_id=tournament_id)
        elif action == 'cancel':
            fight.status = 'cancelled'
            fight.save(update_fields=['status'])
            success, msg = True, "Бой отменён"
        else:
            success, msg = False, "Неизвестное действие"

        if success:
            messages.success(request, msg)
        else:
            messages.error(request, msg)

    return redirect('tournaments:fights_management', tournament_id=tournament_id)


@login_required
@tournament_admin_required
def delete_fight(request, tournament_id, fight_id):
    """Удаление боя (только админ)"""
    fight = get_object_or_404(Fight, pk=fight_id, tournament_id=tournament_id)
    if request.method == 'POST':
        fight.delete()
        messages.success(request, 'Бой удалён')
    return redirect('tournaments:fights_management', tournament_id=tournament_id)


@login_required
@tournament_admin_required
def timer_settings_view(request, tournament_id):
    """Настройки таймера по умолчанию для турнира (только админ)"""
    tournament = get_object_or_404(Tournament, pk=tournament_id)
    settings_obj, created = TimerSettings.objects.get_or_create(
        tournament=tournament,
        defaults={'round_duration': 180, 'break_duration': 60, 'number_of_rounds': 3}
    )

    if request.method == 'POST':
        form = TimerSettingsForm(request.POST, instance=settings_obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Настройки таймера по умолчанию сохранены')
            return redirect('tournaments:tournament_detail', pk=tournament_id)
    else:
        form = TimerSettingsForm(instance=settings_obj)

    return render(request, 'tournaments/timer_settings.html', {
        'form': form, 'tournament': tournament
    })


@login_required
@tournament_admin_required
def advance_winners_view(request, tournament_id):
    """Ручное создание плей-офф из round-robin"""
    from ..models import Bracket
    tournament = get_object_or_404(Tournament, pk=tournament_id)
    bracket_id = request.POST.get('bracket_id')
    if bracket_id:
        bracket = get_object_or_404(Bracket, pk=bracket_id, tournament=tournament)
    else:
        bracket = tournament.brackets.filter(bracket_type='round_robin').first()

    if not bracket:
        messages.error(request, 'Round-robin сетка не найдена')
        return redirect('tournaments:tournament_detail', pk=tournament_id)

    success, msg = FightService.create_playoff_from_round_robin(bracket)
    if success:
        messages.success(request, msg)
    else:
        messages.error(request, msg)

    return redirect('tournaments:bracket_view', tournament_id=tournament_id, bracket_id=bracket.id)


@login_required
@tournament_admin_required
@require_POST
def delete_all_fights(request, tournament_id):
    """Удаление всех боёв турнира (для перегенерации)"""
    tournament = get_object_or_404(Tournament, pk=tournament_id)
    count = tournament.fights.count()
    tournament.fights.all().delete()
    messages.success(request, f'Удалено {count} боёв. Можно заново сгенерировать сетку.')
    return redirect('tournaments:fights_management', tournament_id=tournament_id)


# ==================== JUDGE VIEWS ====================

@login_required
@judge_required
def fight_timer(request, tournament_id, fight_id):
    """Страница таймера для судьи"""
    tournament = get_object_or_404(Tournament, pk=tournament_id)
    fight = get_object_or_404(Fight, pk=fight_id, tournament=tournament)

    # Проверка доступа
    is_head = fight.head_judge == request.user.judge
    is_side = request.user.judge in fight.side_judges.all()
    is_general = fight.judge == request.user.judge

    if not (is_head or is_side or is_general):
        messages.error(request, 'У вас нет прав на ведение этого боя')
        return redirect('tournaments:judge_dashboard')

    if not fight.round_time_remaining:
        fight.round_time_remaining = fight.round_duration
    if not fight.break_time_remaining:
        fight.break_time_remaining = fight.break_duration
    fight.save()

    return render(request, 'tournaments/fight_timer.html', {
        'tournament': tournament,
        'fight': fight,
        'is_head_judge': is_head,
        'is_side_judge': is_side,
    })


@login_required
@judge_required
@require_POST
def timer_control(request, tournament_id, fight_id):
    """AJAX управление таймером и настройками боя"""
    tournament = get_object_or_404(Tournament, pk=tournament_id)
    fight = get_object_or_404(Fight, pk=fight_id, tournament=tournament)

    is_head = fight.head_judge == request.user.judge
    is_side = request.user.judge in fight.side_judges.all()
    is_general = fight.judge == request.user.judge

    if not (is_head or is_side or is_general):
        return JsonResponse({'success': False, 'error': 'Нет прав'})

    try:
        data = json.loads(request.body)
        action = data.get('action')

        # --- Actions для всех судей (только чтение) ---
        if action == 'get_state':
            return JsonResponse({
                'success': True,
                'current_round': fight.current_round,
                'total_rounds': fight.total_rounds,
                'round_time': fight.round_time_remaining,
                'break_time': fight.break_time_remaining,
                'round_duration': fight.round_duration,
                'break_duration': fight.break_duration,
                'is_running': fight.is_round_running,
                'is_break': fight.is_break_running,
            })

        # --- Actions только для главного / общего судьи ---
        if not is_head and not is_general:
            return JsonResponse({'success': False, 'error': 'Только главный судья может управлять таймером'})

        if action == 'start_round':
            fight.is_round_running = True
            fight.is_break_running = False
            fight.timer_started_at = timezone.now()
        elif action == 'pause_round':
            fight.is_round_running = False
        elif action == 'reset_round':
            fight.is_round_running = False
            fight.is_break_running = False
            fight.round_time_remaining = fight.round_duration
            fight.current_round = 1
        elif action == 'start_break':
            fight.is_round_running = False
            fight.is_break_running = True
            fight.break_time_remaining = fight.break_duration
            fight.timer_started_at = timezone.now()
        elif action == 'next_round':
            if fight.current_round < fight.total_rounds:
                fight.current_round += 1
                fight.is_round_running = False
                fight.is_break_running = False
                fight.round_time_remaining = fight.round_duration
            else:
                return JsonResponse({'success': False, 'error': 'Последний раунд'})

        # --- Изменение настроек боя (только главный судья) ---
        elif action == 'update_settings':
            if not is_head:
                return JsonResponse({'success': False, 'error': 'Только главный судья может менять настройки'})
            new_total = data.get('total_rounds')
            new_round_dur = data.get('round_duration')
            new_break_dur = data.get('break_duration')

            if new_total is not None:
                fight.total_rounds = max(1, min(20, int(new_total)))
            if new_round_dur is not None:
                fight.round_duration = max(10, int(new_round_dur))
                if not fight.is_round_running:
                    fight.round_time_remaining = fight.round_duration
            if new_break_dur is not None:
                fight.break_duration = max(5, int(new_break_dur))
                if not fight.is_break_running:
                    fight.break_time_remaining = fight.break_duration

            fight.save()
            return JsonResponse({
                'success': True,
                'total_rounds': fight.total_rounds,
                'round_duration': fight.round_duration,
                'break_duration': fight.break_duration,
                'round_time': fight.round_time_remaining,
                'break_time': fight.break_time_remaining,
            })

        else:
            return JsonResponse({'success': False, 'error': 'Неизвестное действие'})

        fight.save()
        return JsonResponse({
            'success': True,
            'current_round': fight.current_round,
            'total_rounds': fight.total_rounds,
            'round_time': fight.round_time_remaining,
            'break_time': fight.break_time_remaining,
            'round_duration': fight.round_duration,
            'break_duration': fight.break_duration,
        })

    except Exception as e:
        logger.error(f"Ошибка таймера: {e}")
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@judge_required
@require_POST
def complete_fight_ajax(request, tournament_id, fight_id):
    """AJAX завершение боя судьёй"""
    tournament = get_object_or_404(Tournament, pk=tournament_id)
    fight = get_object_or_404(Fight, pk=fight_id, tournament=tournament)

    is_head = fight.head_judge == request.user.judge
    is_general = fight.judge == request.user.judge

    if not (is_head or is_general):
        return JsonResponse({'success': False, 'error': 'Нет прав'})

    try:
        data = json.loads(request.body)
        winner_id = data.get('winner_id')
        method = data.get('method', '')
        scores = data.get('scores', {})

        winner = None
        if winner_id and winner_id != 'draw':
            winner = Fighter.objects.get(pk=winner_id)

        success, msg = FightService.complete_fight(
            fight, winner=winner, method=method, scores=scores
        )
        return JsonResponse({'success': success, 'message': msg})

    except Exception as e:
        logger.error(f"Ошибка завершения боя: {e}")
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@tournament_admin_or_judge_required
def fight_results(request, fight_id):
    """Просмотр результатов завершённого боя"""
    fight = get_object_or_404(
        Fight.objects.select_related(
            'fighter1', 'fighter2', 'winner', 'judge', 'head_judge',
            'tournament', 'age_weight_category'
        ),
        pk=fight_id
    )

    is_admin = (
        request.user.is_superuser or
        (hasattr(request.user, 'profile') and
         request.user.profile.role in ('system_admin', 'tournament_admin'))
    )

    if not is_admin:
        has_access = False
        if hasattr(request.user, 'judge'):
            if fight.judge == request.user.judge:
                has_access = True
            if fight.head_judge == request.user.judge:
                has_access = True
            if request.user.judge in fight.side_judges.all():
                has_access = True
        if not has_access:
            return HttpResponseForbidden("Доступ запрещён.")

    return render(request, 'tournaments/fight_results.html', {'fight': fight})


# ==================== BOXING SCORES ====================

@login_required
@judge_required
def submit_round_score(request, tournament_id, fight_id):
    """Боковой судья выставляет оценку за раунд"""
    tournament = get_object_or_404(Tournament, pk=tournament_id)
    fight = get_object_or_404(Fight, pk=fight_id, tournament=tournament)

    if not tournament.is_boxing:
        return JsonResponse({'success': False, 'error': 'Не боксерский бой'})

    if request.user.judge not in fight.side_judges.all():
        return JsonResponse({'success': False, 'error': 'Вы не боковой судья этого боя'})

    try:
        data = json.loads(request.body)
        round_number = int(data.get('round_number', 1))
        score_f1 = int(data.get('score_fighter1', 0))
        score_f2 = int(data.get('score_fighter2', 0))

        success, msg = FightService.submit_round_score(
            fight, request.user.judge, round_number, score_f1, score_f2
        )
        return JsonResponse({'success': success, 'message': msg})
    except Exception as e:
        logger.error(f"Ошибка оценки: {e}")
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@judge_required
def head_judge_finalize(request, tournament_id, fight_id):
    """Главный судья выбирает победителя по итогам оценок боковых"""
    tournament = get_object_or_404(Tournament, pk=tournament_id)
    fight = get_object_or_404(Fight, pk=fight_id, tournament=tournament)

    if fight.head_judge != request.user.judge:
        return JsonResponse({'success': False, 'error': 'Вы не главный судья'})

    try:
        data = json.loads(request.body)
        winner_id = data.get('winner_id')
        method = data.get('method', 'points')

        winner = None
        if winner_id == 'draw':
            fight.is_draw = True
        elif winner_id:
            winner = Fighter.objects.get(pk=winner_id)

        round_summary = fight.get_total_round_scores()
        scores = round_summary if round_summary else None

        success, msg = FightService.complete_fight(
            fight, winner=winner, method=method, scores=scores
        )
        return JsonResponse({'success': success, 'message': msg})
    except Exception as e:
        logger.error(f"Ошибка финализации: {e}")
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@judge_required
def get_round_scores(request, tournament_id, fight_id):
    """Получить все оценки за раунды"""
    tournament = get_object_or_404(Tournament, pk=tournament_id)
    fight = get_object_or_404(Fight, pk=fight_id, tournament=tournament)

    if not tournament.is_boxing:
        return JsonResponse({'success': False, 'error': 'Не бокс'})

    is_admin = request.user.is_superuser or (
        hasattr(request.user, 'profile') and
        request.user.profile.role in ('system_admin', 'tournament_admin')
    )
    is_head = fight.head_judge and fight.head_judge.user == request.user
    is_side = request.user.judge in fight.side_judges.all() if hasattr(request.user, 'judge') else False

    if not (is_admin or is_head or is_side):
        return JsonResponse({'success': False, 'error': 'Нет доступа'})

    scores = list(fight.round_scores.values(
        'round_number', 'judge__first_name', 'judge__last_name',
        'score_fighter1', 'score_fighter2'
    ))
    summary = fight.get_round_scores_summary()
    return JsonResponse({
        'success': True,
        'scores': scores,
        'summary': summary,
        'totals': fight.get_total_round_scores(),
    })