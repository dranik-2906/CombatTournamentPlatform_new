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
from django.contrib.auth.models import User

logger = logging.getLogger('tournaments')


@login_required
@judge_required
def judge_dashboard(request):
    """Главная панель судьи с фильтрацией"""
    from django.db.models import Q
    from ..models import Tournament, AgeWeightCategory # Импортируем модели для фильтров

    # 1. Базовый queryset (все бои судьи)
    fights_queryset = Fight.objects.filter(
        Q(judge=request.user.judge) |
        Q(head_judge=request.user.judge) |
        Q(side_judges=request.user.judge)
    ).distinct()

    # 2. Получаем параметры фильтров из GET-запроса
    tournament_id = request.GET.get('tournament')
    category_id = request.GET.get('category')

    # 3. Применяем фильтры (одновременно)
    if tournament_id:
        fights_queryset = fights_queryset.filter(tournament_id=tournament_id)
    if category_id:
        fights_queryset = fights_queryset.filter(age_weight_category_id=category_id)

    # 4. Сортируем и оптимизируем запросы к БД
    fights_queryset = fights_queryset.select_related(
        'tournament', 'age_weight_category', 'fighter1', 'fighter2'
    ).order_by('start_time')

    # 5. Разделяем по статусам
    scheduled = fights_queryset.filter(status='scheduled')
    in_progress = fights_queryset.filter(status='in_progress')
    completed = fights_queryset.filter(status='completed')

    # 6. Формируем списки для выпадающих меню (только те турниры/категории, где у судьи есть бои)
    all_judge_fights = Fight.objects.filter(
        Q(judge=request.user.judge) |
        Q(head_judge=request.user.judge) |
        Q(side_judges=request.user.judge)
    ).distinct()

    # Берем уникальные ID турниров и категорий из боёв судьи
    tournament_ids = all_judge_fights.values_list('tournament_id', flat=True).distinct()
    category_ids = all_judge_fights.values_list('age_weight_category_id', flat=True).distinct()

    tournaments = Tournament.objects.filter(id__in=tournament_ids).order_by('name')
    # Исключаем None, если есть бои без категорий
    categories = AgeWeightCategory.objects.filter(id__in=category_ids, id__isnull=False).order_by('name')

    context = {
        'scheduled': scheduled,
        'in_progress': in_progress,
        'completed': completed,
        'tournaments': tournaments,
        'categories': categories,
        'selected_tournament': str(tournament_id) if tournament_id else '',
        'selected_category': str(category_id) if category_id else '',
    }

    return render(request, 'tournaments/judge_dashboard.html', context)

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

    # Безопасно получаем объект судьи (чтобы админ без профиля судьи не ломал страницу)
    user_judge = getattr(request.user, 'judge', None)
    is_admin = request.user.is_superuser or (
                getattr(request.user, 'profile', None) and request.user.profile.role in ['system_admin',
                                                                                         'tournament_admin'])

    # Проверка доступа (с защитой от None)
    is_head = (fight.head_judge == user_judge) if user_judge else False
    is_side = (user_judge in fight.side_judges.all()) if user_judge else False
    is_general = (fight.judge == user_judge) if user_judge else False

    # Администраторы тоже могут заходить и управлять
    if not (is_head or is_side or is_general or is_admin):
        messages.error(request, 'У вас нет прав на ведение этого боя')
        return redirect('tournaments:judge_dashboard')

    # Определяем роль для шаблона
    if is_head or is_admin:
        judge_role = 'head'
    elif is_side:
        judge_role = 'side'
    elif is_general:
        judge_role = 'general'
    else:
        judge_role = 'viewer'

    can_control_timer = is_head or is_general or is_admin

    timer_settings, _ = TimerSettings.objects.get_or_create(
        tournament=fight.tournament,
        defaults={'round_duration': 180, 'break_duration': 60, 'number_of_rounds': 3}
    )

    # Для бокса: подгружаем оценки
    my_scores = []
    if fight.tournament.is_boxing and is_side and user_judge:
        my_scores = list(
            fight.round_scores.filter(judge=user_judge)
            .values('round_number', 'score_fighter1', 'score_fighter2')
        )

    all_scores = []
    if fight.tournament.is_boxing and (is_head or is_admin):
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
                        # ИСПРАВЛЕНИЕ: Берем очки напрямую из POST-запроса, чтобы они точно сохранились
                        'fighter1': int(request.POST.get('score_fighter1') or 0),
                        'fighter2': int(request.POST.get('score_fighter2') or 0),
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
        'can_control_timer': can_control_timer,
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

    user_judge = getattr(request.user, 'judge', None)
    is_admin = request.user.is_superuser or (
                getattr(request.user, 'profile', None) and request.user.profile.role in ['system_admin',
                                                                                         'tournament_admin'])

    # Доступ: любой назначенный судья или админ
    is_assigned = is_admin or (
            user_judge and (
            fight.judge == user_judge or
            fight.head_judge == user_judge or
            user_judge in fight.side_judges.all()
    )
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

    user_judge = getattr(request.user, 'judge', None)
    is_admin = request.user.is_superuser or (
                getattr(request.user, 'profile', None) and request.user.profile.role in ['system_admin',
                                                                                         'tournament_admin'])

    is_assigned = is_admin or (
            user_judge and (
            fight.judge == user_judge or
            fight.head_judge == user_judge or
            user_judge in fight.side_judges.all()
    )
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
    """Добавление нового судьи с автосозданием аккаунта"""
    if request.method == 'POST':
        form = JudgeForm(request.POST)
        if form.is_valid():
            judge = form.save(commit=False)  # Пока не сохраняем в БД

            # 1. Генерируем уникальный логин: judge{порядковый номер}
            count = Judge.objects.count() + 1
            username = f"judge{count}"
            # На всякий случай проверяем, нет ли уже такого логина (если судей удаляли)
            while User.objects.filter(username=username).exists():
                count += 1
                username = f"judge{count}"

            # 2. Генерируем пароль из даты рождения (например, judge2906)
            dob = form.cleaned_data.get('date_of_birth')
            if dob:
                password = f"judge{dob.strftime('%d%m')}"
            else:
                password = "judge1234"  # Если дата не указана

            # 3. Создаем пользователя в системе
            user = User.objects.create_user(username=username, password=password)
            user.first_name = judge.first_name
            user.last_name = judge.last_name
            user.save()

            # 4. Привязываем пользователя к судье и сохраняем
            judge.user = user
            judge.save()

            # Сообщение админу с созданными данными
            messages.success(
                request,
                f'Судья {judge.last_name} добавлен! Логин: {username}, Пароль: {password}'
            )
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