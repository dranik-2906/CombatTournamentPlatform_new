from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from users.decorators import tournament_admin_required, coach_required
from users.models import Profile
from ..models import Fighter, Tournament, TournamentRegistration
import random


# ==================== УПРАВЛЕНИЕ ТРЕНЕРАМИ (ДЛЯ АДМИНА) ====================

@login_required
@tournament_admin_required
def coach_list(request):
    """Список тренеров текущей федерации"""
    # Если суперюзер - видит всех, иначе - только тренеров своей федерации
    if request.user.is_superuser:
        coaches = User.objects.filter(profile__role='coach').select_related('profile')
    else:
        federation = getattr(request.user.profile, 'federation', None)
        coaches = User.objects.filter(profile__role='coach', profile__federation=federation).select_related('profile')

    return render(request, 'tournaments/coach_list.html', {'coaches': coaches})


@login_required
@tournament_admin_required
def add_coach(request):
    """Добавление нового тренера"""
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        club = request.POST.get('club', '').strip()

        if not username or not password:
            messages.error(request, 'Логин и пароль обязательны')
            return redirect('tournaments:add_coach')

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Пользователь с таким логином уже существует')
            return redirect('tournaments:add_coach')

        # Создаем пользователя
        user = User.objects.create_user(
            username=username,
            password=password,
            email=email,
            first_name=first_name,
            last_name=last_name
        )

        # Настраиваем профиль
        profile = user.profile
        profile.role = 'coach'
        profile.club = club
        if not request.user.is_superuser:
            profile.federation = request.user.profile.federation
        profile.save()

        messages.success(request, f'Тренер {first_name} {last_name} успешно добавлен!')
        return redirect('tournaments:coach_list')

    return render(request, 'tournaments/add_coach.html')


@login_required
@tournament_admin_required
def edit_coach(request, coach_id):
    """Редактирование профиля тренера"""
    coach_user = get_object_or_404(User, id=coach_id, profile__role='coach')

    # Проверка прав: админ федерации может редактировать только своих тренеров
    if not request.user.is_superuser:
        if coach_user.profile.federation != request.user.profile.federation:
            messages.error(request, 'Вы можете редактировать только тренеров своей федерации')
            return redirect('tournaments:coach_list')

    if request.method == 'POST':
        coach_user.first_name = request.POST.get('first_name', '').strip()
        coach_user.last_name = request.POST.get('last_name', '').strip()
        coach_user.email = request.POST.get('email', '').strip()

        # Если ввели новый пароль - обновляем
        new_password = request.POST.get('password', '').strip()
        if new_password:
            coach_user.set_password(new_password)

        coach_user.save()

        # Обновляем профиль (клуб)
        profile = coach_user.profile
        profile.club = request.POST.get('club', '').strip()
        profile.save()

        messages.success(request, f'Данные тренера {coach_user.first_name} {coach_user.last_name} обновлены!')
        return redirect('tournaments:coach_list')

    return render(request, 'tournaments/edit_coach.html', {'coach': coach_user})


# ==================== ПАНЕЛЬ ТРЕНЕРА (ДЛЯ САМОГО ТРЕНЕРА) ====================

@login_required
@coach_required
def coach_my_fighters(request):
    """Список бойцов, привязанных к клубу тренера"""
    coach_profile = request.user.profile
    club_name = coach_profile.club

    # Если клуб не указан, показываем пустой список и предупреждение
    if club_name:
        fighters = Fighter.objects.filter(club=club_name).select_related('user')
    else:
        fighters = Fighter.objects.none()
        messages.warning(request, 'В вашем профиле не указан клуб. Пожалуйста, обратитесь к администратору, чтобы он добавил ваш клуб. Без клуба вы не можете добавлять бойцов.')

    return render(request, 'tournaments/coach_my_fighters.html', {
        'fighters': fighters,
    })


@login_required
@coach_required
def coach_add_fighter(request):
    """Добавление бойца тренером (создает заявку со статусом Ожидает)"""
    if request.method == 'POST':
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        weight = request.POST.get('weight')
        date_of_birth = request.POST.get('date_of_birth')
        tournament_id = request.POST.get('tournament_id')

        coach_profile = request.user.profile
        club_name = coach_profile.club

        if not club_name:
            messages.error(request, 'Сначала укажите ваш клуб в профиле.')
            return redirect('tournaments:coach_my_fighters')

        # 1. Создаем пользователя для бойца (генерируем логин)
        random_num = random.randint(1000, 9999)
        username = f"fighter_{random_num}"
        while User.objects.filter(username=username).exists():
            random_num = random.randint(1000, 9999)
            username = f"fighter_{random_num}"

        user = User.objects.create_user(username=username, password='fighter123')

        # 2. Настраиваем профиль бойца
        profile = user.profile
        profile.role = 'fighter'
        profile.club = club_name
        profile.federation = coach_profile.federation  # Наследуем федерацию тренера
        profile.save()

        # 3. Создаем объект Fighter
        fighter = Fighter.objects.create(
            user=user,
            first_name=first_name,
            last_name=last_name,
            weight=weight,
            date_of_birth=date_of_birth,
            club=club_name
        )

        # 4. Создаем заявку на турнир (если выбран турнир)
        if tournament_id:
            tournament = Tournament.objects.get(id=tournament_id)
            TournamentRegistration.objects.create(
                tournament=tournament,
                fighter=fighter,
                is_approved=False    # Заявка сразу создается как "Ожидает"
            )
            messages.success(request, f'Боец {first_name} {last_name} добавлен и подан на турнир "{tournament.name}"!')
        else:
            messages.success(request, f'Боец {first_name} {last_name} успешно добавлен в ваш клуб!')

        # ИСПРАВЛЕНИЕ: Возвращаем редирект после POST, чтобы избежать дублирования при обновлении страницы
        return redirect('tournaments:coach_my_fighters')

    # Для GET-запроса собираем доступные турниры
    if request.user.profile.federation:
        tournaments = Tournament.objects.filter(is_active=True, federation=request.user.profile.federation)
    else:
        tournaments = Tournament.objects.filter(is_active=True)

    return render(request, 'tournaments/coach_add_fighter.html', {'tournaments': tournaments})


@login_required
@coach_required
def coach_import_excel(request):
    """Импорт бойцов тренером из Excel (заглушка страницы)"""
    if request.method == 'POST':
        # Логику парсинга Excel можно добавить позже по аналогии с админской
        messages.info(request, 'Импорт Excel для тренеров находится в разработке.')
        return redirect('tournaments:coach_my_fighters')

    return render(request, 'tournaments/coach_import_excel.html')


@login_required
@coach_required
def coach_apply_tournament(request):
    """Массовая подача заявок на турнир"""
    coach_profile = request.user.profile
    club_name = coach_profile.club

    if not club_name:
        messages.error(request, 'У вас не указан клуб.')
        return redirect('tournaments:coach_my_fighters')

    fighters = Fighter.objects.filter(club=club_name)

    if request.method == 'POST':
        tournament_id = request.POST.get('tournament_id')
        fighter_ids = request.POST.getlist('fighters')  # Получаем список ID бойцов из чекбоксов

        if not tournament_id or not fighter_ids:
            messages.error(request, 'Выберите турнир и хотя бы одного бойца.')
            return redirect('tournaments:coach_apply_tournament')

        tournament = get_object_or_404(Tournament, id=tournament_id)
        added_count = 0

        for f_id in fighter_ids:
            fighter = get_object_or_404(Fighter, id=f_id)
            # Проверяем, не подан ли уже
            if not TournamentRegistration.objects.filter(tournament=tournament, fighter=fighter).exists():
                TournamentRegistration.objects.create(
                    tournament=tournament,
                    fighter=fighter,
                    is_approved=False
                )
                added_count += 1

        messages.success(request, f'Успешно подано {added_count} заявок на турнир "{tournament.name}"!')
        return redirect('tournaments:coach_my_fighters')

    # Для GET запроса
    tournaments = Tournament.objects.filter(is_active=True)
    return render(request, 'tournaments/coach_apply_tournament.html', {
        'fighters': fighters,
        'tournaments': tournaments
    })


@login_required
@coach_required
def coach_edit_fighter(request, fighter_id):
    """Редактирование бойца тренером"""
    fighter = get_object_or_404(Fighter, id=fighter_id)

    # Проверка, что боец из клуба этого тренера
    if fighter.club != request.user.profile.club:
        messages.error(request, 'Вы можете редактировать только своих бойцов')
        return redirect('tournaments:coach_my_fighters')

    if request.method == 'POST':
        fighter.first_name = request.POST.get('first_name')
        fighter.last_name = request.POST.get('last_name')
        fighter.weight = request.POST.get('weight')
        fighter.date_of_birth = request.POST.get('date_of_birth')
        fighter.save()

        messages.success(request, 'Данные бойца обновлены!')
        return redirect('tournaments:coach_my_fighters')

    return render(request, 'tournaments/coach_edit_fighter.html', {'fighter': fighter})


@login_required
@coach_required
def coach_delete_fighter(request, fighter_id):
    """Удаление бойца тренером"""
    fighter = get_object_or_404(Fighter, id=fighter_id)

    if fighter.club != request.user.profile.club:
        messages.error(request, 'Вы можете удалять только своих бойцов')
        return redirect('tournaments:coach_my_fighters')

    if request.method == 'POST':
        user = fighter.user  # Запоминаем пользователя
        fighter.delete()  # Удаляем бойца
        user.delete()  # Удаляем аккаунт пользователя
        messages.success(request, 'Боец удален из системы.')
        return redirect('tournaments:coach_my_fighters')

    return render(request, 'tournaments/coach_delete_fighter.html', {'fighter': fighter})


@login_required
@tournament_admin_required
def delete_coach(request, coach_id):
    """Удаление тренера"""
    coach_user = get_object_or_404(User, id=coach_id, profile__role='coach')

    # Проверка прав: админ федерации может удалять только своих тренеров
    if not request.user.is_superuser:
        if coach_user.profile.federation != request.user.profile.federation:
            messages.error(request, 'Вы можете удалять только тренеров своей федерации')
            return redirect('tournaments:coach_list')

    if request.method == 'POST':
        name = f"{coach_user.first_name} {coach_user.last_name}".strip()

        # Удаляем пользователя (профиль удалится автоматически благодаря CASCADE в модели)
        coach_user.delete()

        messages.success(request, f'Тренер {name} успешно удален из системы.')
        return redirect('tournaments:coach_list')

    # Если это GET-запрос (хотя мы будем удалять через POST), покажем страницу подтверждения
    return render(request, 'tournaments/confirm_delete_coach.html', {'coach': coach_user})