import uuid
from decimal import Decimal, InvalidOperation
from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.utils.crypto import get_random_string
from users.decorators import tournament_admin_required, coach_required
from ..models import Fighter, Tournament, TournamentRegistration


# ==================== УПРАВЛЕНИЕ ТРЕНЕРАМИ (ДЛЯ АДМИНА) ====================

@login_required
@tournament_admin_required
def coach_list(request):
    """Список тренеров текущей федерации"""
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

        user = User.objects.create_user(
            username=username,
            password=password,
            email=email,
            first_name=first_name,
            last_name=last_name
        )

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

    if not request.user.is_superuser:
        if coach_user.profile.federation != request.user.profile.federation:
            messages.error(request, 'Вы можете редактировать только тренеров своей федерации')
            return redirect('tournaments:coach_list')

    if request.method == 'POST':
        coach_user.first_name = request.POST.get('first_name', '').strip()
        coach_user.last_name = request.POST.get('last_name', '').strip()
        coach_user.email = request.POST.get('email', '').strip()

        new_password = request.POST.get('password', '').strip()
        if new_password:
            coach_user.set_password(new_password)

        coach_user.save()

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

    if club_name:
        fighters = Fighter.objects.filter(club=club_name).select_related('user')
    else:
        fighters = Fighter.objects.none()
        messages.warning(request, 'В вашем профиле не указан клуб. Пожалуйста, обратитесь к администратору.')

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
        weight_raw = request.POST.get('weight')
        date_of_birth_raw = request.POST.get('date_of_birth')
        gender = request.POST.get('gender')  # ИСПРАВЛЕНИЕ: добавлен пол
        tournament_id = request.POST.get('tournament_id')

        coach_profile = request.user.profile
        club_name = coach_profile.club

        if not club_name:
            messages.error(request, 'Сначала укажите ваш клуб в профиле.')
            return redirect('tournaments:coach_my_fighters')

        # Парсинг веса и даты
        try:
            weight = Decimal(weight_raw.replace(',', '.'))
            date_of_birth = datetime.strptime(date_of_birth_raw, '%Y-%m-%d').date()
        except (InvalidOperation, ValueError):
            messages.error(request, 'Неверный формат веса или даты.')
            return redirect('tournaments:coach_add_fighter')

        # Валидация через модель
        candidate = Fighter(
            first_name=first_name, last_name=last_name,
            weight=weight, date_of_birth=date_of_birth, gender=gender, club=club_name
        )
        try:
            candidate.full_clean()
        except ValidationError as e:
            messages.error(request, f'Ошибка валидации: {e.messages}')
            return redirect('tournaments:coach_add_fighter')

        # Генерация уникального логина и пароля
        username = f"fighter_{uuid.uuid4().hex[:10]}"
        password = get_random_string(length=10)

        user = User.objects.create_user(username=username, password=password)

        profile = user.profile
        profile.role = 'fighter'
        profile.club = club_name
        profile.federation = coach_profile.federation
        profile.save()

        fighter = Fighter.objects.create(
            user=user,
            first_name=first_name,
            last_name=last_name,
            weight=weight,
            date_of_birth=date_of_birth,
            gender=gender,  # ИСПРАВЛЕНИЕ
            club=club_name
        )

        if tournament_id:
            tournament = Tournament.objects.get(id=tournament_id)
            TournamentRegistration.objects.create(
                tournament=tournament,
                fighter=fighter,
                is_approved=False
            )
            messages.success(request, f'Боец {first_name} {last_name} добавлен. Логин: {username}, Пароль: {password}')
        else:
            messages.success(request, f'Боец {first_name} {last_name} добавлен. Логин: {username}, Пароль: {password}')

        return redirect('tournaments:coach_my_fighters')

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
        fighter_ids = request.POST.getlist('fighters')

        if not tournament_id or not fighter_ids:
            messages.error(request, 'Выберите турнир и хотя бы одного бойца.')
            return redirect('tournaments:coach_apply_tournament')

        tournament = get_object_or_404(Tournament, id=tournament_id)
        added_count = 0

        for f_id in fighter_ids:
            fighter = get_object_or_404(Fighter, id=f_id)
            if not TournamentRegistration.objects.filter(tournament=tournament, fighter=fighter).exists():
                TournamentRegistration.objects.create(
                    tournament=tournament,
                    fighter=fighter,
                    is_approved=False
                )
                added_count += 1

        messages.success(request, f'Успешно подано {added_count} заявок на турнир "{tournament.name}"!')
        return redirect('tournaments:coach_my_fighters')

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

    if fighter.club != request.user.profile.club:
        messages.error(request, 'Вы можете редактировать только своих бойцов')
        return redirect('tournaments:coach_my_fighters')

    if request.method == 'POST':
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        weight_raw = request.POST.get('weight')
        date_of_birth_raw = request.POST.get('date_of_birth')

        try:
            weight = Decimal(weight_raw.replace(',', '.'))
            date_of_birth = datetime.strptime(date_of_birth_raw, '%Y-%m-%d').date()
        except (InvalidOperation, ValueError):
            messages.error(request, 'Неверный формат веса или даты.')
            return redirect('tournaments:coach_edit_fighter', fighter_id=fighter.id)

        fighter.first_name = first_name
        fighter.last_name = last_name
        fighter.weight = weight
        fighter.date_of_birth = date_of_birth

        try:
            fighter.full_clean()
            fighter.save()
        except ValidationError as e:
            messages.error(request, f'Ошибка валидации: {e.messages}')
            return redirect('tournaments:coach_edit_fighter', fighter_id=fighter.id)

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
        user = fighter.user
        user.delete()  # Каскадно удалит и Fighter
        messages.success(request, 'Боец удален из системы.')
        return redirect('tournaments:coach_my_fighters')

    return render(request, 'tournaments/coach_delete_fighter.html', {'fighter': fighter})


@login_required
@tournament_admin_required
def delete_coach(request, coach_id):
    """Удаление тренера"""
    coach_user = get_object_or_404(User, id=coach_id, profile__role='coach')

    if not request.user.is_superuser:
        if coach_user.profile.federation != request.user.profile.federation:
            messages.error(request, 'Вы можете удалять только тренеров своей федерации')
            return redirect('tournaments:coach_list')

    if request.method == 'POST':
        name = f"{coach_user.first_name} {coach_user.last_name}".strip()
        coach_user.delete()
        messages.success(request, f'Тренер {name} успешно удален из системы.')
        return redirect('tournaments:coach_list')

    return render(request, 'tournaments/confirm_delete_coach.html', {'coach': coach_user})