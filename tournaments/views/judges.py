import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from users.decorators import judge_required, tournament_admin_required
from ..models import Fight, TimerSettings, Judge
from ..forms import FightResultForm, JudgeForm
from ..services import FightService

logger = logging.getLogger('tournaments')


@login_required
@judge_required
def judge_dashboard(request):
    """Главная панель судьи"""
    fights = Fight.objects.filter(
        judge=request.user.judge
    ).select_related('tournament', 'bracket', 'fighter1', 'fighter2').order_by('start_time')

    scheduled = fights.filter(status='scheduled')
    in_progress = fights.filter(status='in_progress')
    completed = fights.filter(status='completed')

    return render(request, 'tournaments/judge_dashboard.html', {
        'scheduled': scheduled,
        'in_progress': in_progress,
        'completed': completed,
    })


@login_required
@judge_required
def judge_my_fights(request):
    """Список боёв судьи"""
    fights = Fight.objects.filter(
        judge=request.user.judge
    ).select_related('tournament', 'bracket', 'fighter1', 'fighter2').order_by('-created_at')

    return render(request, 'tournaments/judge_my_fights.html', {
        'fights': fights,
    })


@login_required
@judge_required
def judge_fight_panel(request, fight_id):
    """Панель ведения боя"""
    fight = get_object_or_404(
        Fight.objects.select_related('fighter1', 'fighter2', 'tournament', 'bracket'),
        pk=fight_id, judge=request.user.judge
    )

    timer_settings, _ = TimerSettings.objects.get_or_create(
        tournament=fight.tournament,
        defaults={'round_duration': 180, 'break_duration': 60, 'number_of_rounds': 3}
    )

    if request.method == 'POST':
        # Редактирование настроек таймера
        if 'update_timer' in request.POST:
            try:
                timer_settings.round_duration = max(10, int(request.POST.get('round_duration', 180)))
                timer_settings.break_duration = max(5, int(request.POST.get('break_duration', 60)))
                timer_settings.number_of_rounds = max(1, min(20, int(request.POST.get('number_of_rounds', 3))))
                timer_settings.save()
                messages.success(request, 'Настройки таймера обновлены')
            except (ValueError, TypeError):
                messages.error(request, 'Неверные значения таймера')
            return redirect('tournaments:judge_fight_panel', fight_id=fight_id)

        # Завершение боя через FightService
        form = FightResultForm(request.POST, instance=fight, fight=fight)
        if form.is_valid():
            winner = form.cleaned_data.get('winner')
            try:
                success, msg = FightService.complete_fight(
                    fight,
                    winner=winner,
                    method=form.cleaned_data.get('win_method', ''),
                    notes=form.cleaned_data.get('judge_notes', ''),
                    scores={
                        'fighter1': form.cleaned_data.get('score_fighter1', 0),
                        'fighter2': form.cleaned_data.get('score_fighter2', 0),
                    }
                )
                if success:
                    messages.success(request, msg)
                else:
                    messages.error(request, msg)
                return redirect('tournaments:judge_dashboard')
            except Exception as e:
                logger.exception("Fight completion error")
                messages.error(request, f"Ошибка завершения боя: {e}")
        else:
            messages.error(request, 'Ошибка в форме результата')
    else:
        form = FightResultForm(instance=fight, fight=fight)

    return render(request, 'tournaments/judge_fight_panel.html', {
        'fight': fight,
        'form': form,
        'timer_settings': timer_settings,
    })


@login_required
@judge_required
def judge_update_result(request, tournament_id, fight_id):
    """Обновление результата судьёй (использует FightService)"""
    fight = get_object_or_404(
        Fight, pk=fight_id, tournament_id=tournament_id, judge=request.user.judge
    )

    if request.method == 'POST':
        form = FightResultForm(request.POST, instance=fight, fight=fight)
        if form.is_valid():
            winner = form.cleaned_data.get('winner')
            try:
                success, msg = FightService.complete_fight(
                    fight,
                    winner=winner,
                    method=form.cleaned_data.get('win_method', ''),
                    notes=form.cleaned_data.get('judge_notes', ''),
                    scores={
                        'fighter1': form.cleaned_data.get('score_fighter1', 0),
                        'fighter2': form.cleaned_data.get('score_fighter2', 0),
                    }
                )
                if success:
                    messages.success(request, msg)
                else:
                    messages.error(request, msg)
            except Exception as e:
                logger.exception("Fight update error")
                messages.error(request, f"Ошибка: {e}")
        else:
            messages.error(request, 'Ошибка в форме')
        return redirect('tournaments:judge_dashboard')

    return redirect('tournaments:judge_dashboard')


@login_required
@judge_required
def update_judge_notes(request, tournament_id, fight_id):
    """Обновление заметок судьи"""
    fight = get_object_or_404(
        Fight, pk=fight_id, tournament_id=tournament_id, judge=request.user.judge
    )

    if request.method == 'POST':
        notes = request.POST.get('judge_notes', '')
        fight.judge_notes = notes
        fight.save(update_fields=['judge_notes'])
        messages.success(request, 'Заметки сохранены')

    return redirect('tournaments:judge_fight_panel', fight_id=fight_id)


@login_required
@judge_required
def fight_timer(request, tournament_id, fight_id):
    """Страница таймера боя"""
    fight = get_object_or_404(
        Fight, pk=fight_id, tournament_id=tournament_id, judge=request.user.judge
    )
    timer_settings, _ = TimerSettings.objects.get_or_create(
        tournament=fight.tournament,
        defaults={'round_duration': 180, 'break_duration': 60, 'number_of_rounds': 3}
    )
    return render(request, 'tournaments/fight_timer.html', {
        'fight': fight,
        'timer_settings': timer_settings,
    })


@login_required
@judge_required
def timer_control(request, tournament_id, fight_id):
    """AJAX управление таймером (фоновый лог)"""
    fight = get_object_or_404(
        Fight, pk=fight_id, tournament_id=tournament_id, judge=request.user.judge
    )

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

    action = data.get('action')

    timer_settings, _ = TimerSettings.objects.get_or_create(
        tournament=fight.tournament,
        defaults={'round_duration': 180, 'break_duration': 60, 'number_of_rounds': 3}
    )

    if action == 'start_round':
        return JsonResponse({
            'status': 'ok',
            'action': 'round_started',
            'round_duration': timer_settings.round_duration,
        })
    elif action == 'pause_round':
        return JsonResponse({'status': 'ok', 'action': 'round_paused'})
    elif action == 'reset_round':
        return JsonResponse({
            'status': 'ok',
            'action': 'round_reset',
            'round_duration': timer_settings.round_duration,
        })
    elif action == 'next_round':
        return JsonResponse({
            'status': 'ok',
            'action': 'next_round',
            'round_duration': timer_settings.round_duration,
            'number_of_rounds': timer_settings.number_of_rounds,
        })
    elif action == 'start_break':
        return JsonResponse({
            'status': 'ok',
            'action': 'break_started',
            'break_duration': timer_settings.break_duration,
        })

    return JsonResponse({'status': 'error', 'message': 'Unknown action'})


@login_required
@judge_required
def complete_fight_ajax(request, tournament_id, fight_id):
    """AJAX завершение боя из таймера (использует FightService)"""
    fight = get_object_or_404(
        Fight, pk=fight_id, tournament_id=tournament_id, judge=request.user.judge
    )

    winner_id = request.POST.get('winner_id')
    winner = None
    if winner_id:
        if int(winner_id) == fight.fighter1_id:
            winner = fight.fighter1
        elif fight.fighter2_id and int(winner_id) == fight.fighter2_id:
            winner = fight.fighter2

    try:
        success, msg = FightService.complete_fight(
            fight,
            winner=winner,
            method=request.POST.get('win_method', ''),
            notes=request.POST.get('judge_notes', ''),
            scores={
                'fighter1': int(request.POST.get('score_fighter1', 0)),
                'fighter2': int(request.POST.get('score_fighter2', 0)),
            }
        )
        if success:
            return JsonResponse({'status': 'ok', 'message': msg})
        else:
            return JsonResponse({'status': 'error', 'message': msg})
    except Exception as e:
        logger.exception("AJAX fight completion error")
        return JsonResponse({'status': 'error', 'message': str(e)})


# ==================== УПРАВЛЕНИЕ СУДЬЯМИ (АДМИН) ====================

@login_required
@tournament_admin_required
def judge_list(request):
    """Список всех судей"""
    judges = Judge.objects.select_related('user').all().order_by('last_name', 'first_name')
    return render(request, 'tournaments/judge_list.html', {'judges': judges})


@login_required
@tournament_admin_required
def add_judge(request):
    """Добавление нового судьи"""
    if request.method == 'POST':
        form = JudgeForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Судья добавлен')
            return redirect('tournaments:judge_list')
    else:
        form = JudgeForm()
    return render(request, 'tournaments/add_judge.html', {'form': form})


@login_required
@tournament_admin_required
def edit_judge(request, judge_id):
    """Редактирование судьи"""
    judge = get_object_or_404(Judge, pk=judge_id)
    if request.method == 'POST':
        form = JudgeForm(request.POST, instance=judge)
        if form.is_valid():
            form.save()
            messages.success(request, 'Судья обновлён')
            return redirect('tournaments:judge_list')
    else:
        form = JudgeForm(instance=judge)
    return render(request, 'tournaments/edit_judge.html', {'form': form, 'judge': judge})


@login_required
@tournament_admin_required
def toggle_judge_active(request, judge_id):
    """Активация/деактивация судьи"""
    judge = get_object_or_404(Judge, pk=judge_id)
    judge.is_active = not judge.is_active
    judge.save()
    status = 'активирован' if judge.is_active else 'деактивирован'
    messages.success(request, f'Судья {judge.full_name} {status}')
    return redirect('tournaments:judge_list')