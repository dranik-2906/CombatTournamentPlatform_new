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
    from django.db.models import Q
    fights = Fight.objects.filter(
        Q(judge=request.user.judge) |
        Q(head_judge=request.user.judge) |
        Q(side_judges=request.user.judge)
    ).distinct().select_related('tournament', 'bracket', 'fighter1', 'fighter2').order_by('start_time')

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
    from django.db.models import Q
    fights = Fight.objects.filter(
        Q(judge=request.user.judge) |
        Q(head_judge=request.user.judge) |
        Q(side_judges=request.user.judge)
    ).distinct().select_related('tournament', 'bracket', 'fighter1', 'fighter2').order_by('-created_at')

    return render(request, 'tournaments/judge_my_fights.html', {
        'fights': fights,
    })


@login_required
@judge_required
def judge_fight_panel(request, fight_id):
    """Панель ведения боя — разделена на head/side/general"""
    fight = get_object_or_404(
        Fight.objects.select_related('fighter1', 'fighter2', 'tournament', 'bracket', 'head_judge'),
        pk=fight_id
    )

    # Проверка доступа
    is_head = fight.head_judge == request.user.judge
    is_side = request.user.judge in fight.side_judges.all()
    is_general = fight.judge == request.user.judge

    if not (is_head or is_side or is_general):
        messages.error(request, 'У вас нет прав на ведение этого боя')
        return redirect('tournaments:judge_dashboard')

    # Определяем роль для шаблона
    judge_role = 'head' if is_head else ('side' if is_side else 'general')

    timer_settings, _ = TimerSettings.objects.get_or_create(
        tournament=fight.tournament,
        defaults={'round_duration': 180, 'break_duration': 60, 'number_of_rounds': 3}
    )

    # Для бокса: подгружаем оценки
    my_scores = []
    if fight.tournament.is_boxing and is_side:
        my_scores = list(
            fight.round_scores.filter(judge=request.user.judge)
            .values('round_number', 'score_fighter1', 'score_fighter2')
        )

    all_scores = []
    if fight.tournament.is_boxing and is_head:
        all_scores = list(
            fight.round_scores.select_related('judge').values(
                'round_number', 'judge__first_name', 'judge__last_name',
                'score_fighter1', 'score_fighter2'
            )
        )

    if request.method == 'POST':
        # Редактирование настроек таймера (fallback POST, основной способ — AJAX)
        if 'update_timer' in request.POST:
            try:
                ts, _ = TimerSettings.objects.get_or_create(tournament=fight.tournament)
                ts.round_duration = max(10, int(request.POST.get('round_duration', 180)))
                ts.break_duration = max(5, int(request.POST.get('break_duration', 60)))
                ts.number_of_rounds = max(1, min(20, int(request.POST.get('number_of_rounds', 3))))
                ts.save()
                messages.success(request, 'Настройки таймера по умолчанию обновлены')
            except (ValueError, TypeError):
                messages.error(request, 'Неверные значения таймера')
            return redirect('tournaments:judge_fight_panel', fight_id=fight_id)

        # Завершение боя
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
        'judge_role': judge_role,
        'is_head_judge': is_head,
        'is_side_judge': is_side,
        'is_boxing': fight.tournament.is_boxing,
        'my_scores': my_scores,
        'all_scores': all_scores,
        'rounds_range': range(1, fight.total_rounds + 1),
    })


@login_required
@judge_required
def judge_update_result(request, tournament_id, fight_id):
    """Обновление результата судьёй"""
    fight = get_object_or_404(
        Fight, pk=fight_id, tournament_id=tournament_id,
    )
    # Доступ: любой назначенный судья
    is_assigned = (
        fight.judge == request.user.judge or
        fight.head_judge == request.user.judge or
        request.user.judge in fight.side_judges.all()
    )
    if not is_assigned:
        messages.error(request, 'Нет прав')
        return redirect('tournaments:judge_dashboard')

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
        Fight, pk=fight_id, tournament_id=tournament_id,
    )
    is_assigned = (
        fight.judge == request.user.judge or
        fight.head_judge == request.user.judge or
        request.user.judge in fight.side_judges.all()
    )
    if not is_assigned:
        messages.error(request, 'Нет прав')
        return redirect('tournaments:judge_dashboard')

    if request.method == 'POST':
        notes = request.POST.get('judge_notes', '')
        fight.judge_notes = notes
        fight.save(update_fields=['judge_notes'])
        messages.success(request, 'Заметки сохранены')

    return redirect('tournaments:judge_fight_panel', fight_id=fight_id)


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