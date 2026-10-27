"""
load_test_data.py
=================
Скрипт для загрузки тестовых данных в Combat Tournament Platform.
Создаёт: пользователей, судей (главный + боковые), бойцов, турниры (бокс и самбо),
сетки, бои с результатами, оценки раундов (для бокса).

Особенности:
- Главный судья может остановить бой при нокауте и назначить победу
  без учёта оценок боковых судей
- Для бокса: RoundScore с оценками боковых судей за каждый раунд
- Для самбо: болевые приёмы, удержания, дисквалификации
"""

import os
import sys
import django
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'combat_platform.settings')
django.setup()

from tournaments.models.tournament import Tournament
from tournaments.models.fighter import Fighter
from tournaments.models.judge import Judge
from tournaments.models.bracket import Bracket
from tournaments.models.fight import Fight, RoundScore
from tournaments.models.category import AgeWeightCategory

try:
    from users.models import Profile
except ImportError:
    Profile = None

User = get_user_model()


# =============================================================================
# УТИЛИТЫ
# =============================================================================

def create_user(username, email, password, role=None, **extra):
    """Создать пользователя и опционально Profile с ролью."""
    user, created = User.objects.get_or_create(
        username=username,
        defaults={'email': email, **extra}
    )
    user.set_password(password)
    user.save()
    if Profile and role:
        Profile.objects.get_or_create(user=user, defaults={'role': role})
    return user


def create_judge(user, first_name, last_name, judge_type, category='1',
                 license_number='LIC-001', experience_years=5):
    """Создать судью."""
    judge, _ = Judge.objects.get_or_create(
        user=user,
        defaults={
            'first_name': first_name,
            'last_name': last_name,
            'judge_type': judge_type,
            'category': category,
            'license_number': license_number,
            'experience_years': experience_years,
            'is_active': True,
        }
    )
    return judge


def create_fighter(user, first_name, last_name, weight, age,
                   club='Боевой клуб', coach='Тренер Иванов', gender='M'):
    """Создать бойца."""
    fighter, _ = Fighter.objects.get_or_create(
        user=user,
        defaults={
            'first_name': first_name,
            'last_name': last_name,
            'date_of_birth': timezone.now().date() - timedelta(days=365 * age),
            'weight': weight,
            'club': club,
            'coach': coach,
            'gender': gender,
        }
    )
    return fighter


def create_tournament(name, sport_type, **kwargs):
    """Создать турнир."""
    defaults = {
        'description': f'Тестовый турнир по {sport_type}',
        'start_date': timezone.now().date() - timedelta(days=1),
        'end_date': timezone.now().date() + timedelta(days=2),
        'location': 'Москва, Дворец спорта',
        'is_active': True,
        'bracket_type': 'single_elimination',
    }
    defaults.update(kwargs)
    tournament, _ = Tournament.objects.get_or_create(
        name=name,
        defaults=defaults
    )
    return tournament


def create_bracket(tournament, size=4, **kwargs):
    """Создать сетку."""
    defaults = {
        'bracket_type': 'single_elimination',
        'size': size,
        'current_round': 1,
        'total_rounds': 2,
        'status': 'in_progress',
    }
    defaults.update(kwargs)
    bracket, _ = Bracket.objects.get_or_create(
        tournament=tournament,
        defaults=defaults
    )
    return bracket


def create_fight(tournament, bracket, fighter1, fighter2, round_number,
                 match_number, head_judge, side_judges=None, **kwargs):
    """Создать бой."""
    defaults = {
        'tournament': tournament,
        'fighter1': fighter1,
        'fighter2': fighter2,
        'status': 'scheduled',
        'round_number': round_number,
        'match_number': match_number,
        'head_judge': head_judge,
        'total_rounds': 3 if tournament.is_boxing else 1,
        'round_duration': 180 if tournament.is_boxing else 300,
        'break_duration': 60,
    }
    defaults.update(kwargs)
    fight, _ = Fight.objects.get_or_create(
        bracket=bracket,
        round_number=round_number,
        match_number=match_number,
        defaults=defaults
    )
    if side_judges:
        fight.side_judges.set(side_judges)
    return fight


def add_round_scores(fight, judge, round_number, score_f1, score_f2):
    """Добавить оценку бокового судьи за раунд (только для бокса)."""
    RoundScore.objects.get_or_create(
        fight=fight,
        judge=judge,
        round_number=round_number,
        defaults={
            'score_fighter1': score_f1,
            'score_fighter2': score_f2,
        }
    )


def stop_fight_by_head_judge(fight, winner, method, notes=''):
    """
    Остановить бой главным судьёй (например, при нокауте).
    Главный судья выбирает способ победы без учёта оценок боковых судей.
    """
    fight.status = 'completed'
    fight.end_time = timezone.now()
    fight.winner = winner
    fight.win_method = method
    fight.judge_notes = notes
    fight.is_round_running = False
    fight.is_break_running = False
    fight.save()
    print(f"  🛑 Главный судья остановил бой #{fight.id} | "
          f"Победитель: {winner} | Способ: {method}")
    return fight


def complete_fight_by_points(fight, winner, scores, notes=''):
    """Завершить бой по очкам (с учётом оценок боковых судей)."""
    fight.status = 'completed'
    fight.end_time = timezone.now()
    fight.winner = winner
    fight.win_method = 'points'
    fight.score_fighter1 = scores.get('fighter1', 0)
    fight.score_fighter2 = scores.get('fighter2', 0)
    fight.judge_notes = notes
    fight.is_round_running = False
    fight.is_break_running = False
    fight.save()
    print(f"  ✅ Бой #{fight.id} завершён по очкам | "
          f"Счёт: {fight.score_fighter1}:{fight.score_fighter2}")
    return fight


# =============================================================================
# СОЗДАНИЕ ТЕСТОВЫХ ДАННЫХ
# =============================================================================

def create_test_data():
    print("=" * 60)
    print("🚀 Начинаем создание тестовых данных...")
    print("=" * 60)

    # --- 1. АДМИНИСТРАТОР ---
    admin = create_user('admin', 'admin@test.com', 'admin123',
                        role='system_admin', is_superuser=True, is_staff=True)
    print(f"✅ Администратор: {admin.username} / admin123")

    # --- 2. СУДЬИ ---
    # Главный судья
    head_judge_user = create_user('head_judge', 'head_judge@test.com', 'judge123', role='judge')
    head_judge = create_judge(
        head_judge_user, 'Иван', 'Судьин', judge_type='head',
        license_number='LIC-HEAD-001', experience_years=10
    )

    # Боковые судьи (для бокса)
    side_judge1_user = create_user('side_judge1', 'side1@test.com', 'judge123', role='judge')
    side_judge1 = create_judge(
        side_judge1_user, 'Пётр', 'Сторонин', judge_type='side',
        license_number='LIC-SIDE-001', experience_years=5
    )

    side_judge2_user = create_user('side_judge2', 'side2@test.com', 'judge123', role='judge')
    side_judge2 = create_judge(
        side_judge2_user, 'Алексей', 'Боковой', judge_type='side',
        license_number='LIC-SIDE-002', experience_years=7
    )

    side_judge3_user = create_user('side_judge3', 'side3@test.com', 'judge123', role='judge')
    side_judge3 = create_judge(
        side_judge3_user, 'Сергей', 'Угловой', judge_type='side',
        license_number='LIC-SIDE-003', experience_years=4
    )

    # Рефери (для самбо)
    referee_user = create_user('referee', 'referee@test.com', 'judge123', role='judge')
    referee = create_judge(
        referee_user, 'Дмитрий', 'Реферов', judge_type='referee',
        license_number='LIC-REF-001', experience_years=8
    )

    print(f"✅ Судьи созданы: Главный ({head_judge}), "
          f"Боковые ({side_judge1}, {side_judge2}, {side_judge3}), "
          f"Рефери ({referee})")

    # --- 3. БОЙЦЫ ---
    fighters_data = [
        ('boxer1', 'Петр', 'Боксёров', 75.5, 25, 'Боксёрский клуб'),
        ('boxer2', 'Алексей', 'Молотов', 80.0, 22, 'Спартак'),
        ('boxer3', 'Сергей', 'Кузнецов', 70.0, 28, 'Динамо'),
        ('boxer4', 'Андрей', 'Смирнов', 85.0, 30, 'Локомотив'),
        ('sambo1', 'Иван', 'Самбистов', 82.0, 26, 'Самбо-70'),
        ('sambo2', 'Михаил', 'Борцов', 78.0, 24, 'ЦСКА'),
        ('sambo3', 'Николай', 'Бросов', 85.0, 29, 'Динамо'),
        ('sambo4', 'Олег', 'Ломов', 90.0, 31, 'Локомотив'),
    ]

    fighters = {}
    for username, first_name, last_name, weight, age, club in fighters_data:
        user = create_user(username, f'{username}@test.com', 'fighter123', role='fighter')
        fighter = create_fighter(user, first_name, last_name, weight, age, club=club)
        fighters[username] = fighter

    print(f"✅ Бойцы созданы: {len(fighters)} человек")

    # =============================================================================
    # БОКС
    # =============================================================================
    print("\n" + "=" * 60)
    print("🥊 СОЗДАЁМ ТУРНИР ПО БОКСУ")
    print("=" * 60)

    boxing_tournament = create_tournament(
        'Тестовый турнир по боксу "Золотой пояс"',
        sport_type='boxing',
        location='Москва, Дворец бокса'
    )
    boxing_bracket = create_bracket(boxing_tournament, size=4)

    # --- Бой 1: Бокс — завершён по очкам (3 раунда, оценки боковых судей) ---
    boxing_fight1 = create_fight(
        boxing_tournament, boxing_bracket,
        fighters['boxer1'], fighters['boxer3'],
        round_number=1, match_number=1,
        head_judge=head_judge,
        side_judges=[side_judge1, side_judge2, side_judge3],
        status='completed',
        start_time=timezone.now() - timedelta(hours=2),
    )

    # Оценки боковых судей за 3 раунда
    for round_num in range(1, 4):
        add_round_scores(boxing_fight1, side_judge1, round_num, 10, 9)
        add_round_scores(boxing_fight1, side_judge2, round_num, 10, 9)
        add_round_scores(boxing_fight1, side_judge3, round_num, 10, 8)

    # Итоговый счёт по сумме всех оценок: boxer1 = 90, boxer3 = 78
    complete_fight_by_points(
        boxing_fight1,
        winner=fighters['boxer1'],
        scores={'fighter1': 90, 'fighter2': 78},
        notes='Единогласное решение судей. Чистая победа по очкам.'
    )

    # --- Бой 2: Бокс — нокаут в 2-м раунде, главный судья останавливает бой ---
    boxing_fight2 = create_fight(
        boxing_tournament, boxing_bracket,
        fighters['boxer2'], fighters['boxer4'],
        round_number=1, match_number=2,
        head_judge=head_judge,
        side_judges=[side_judge1, side_judge2, side_judge3],
        status='in_progress',
        start_time=timezone.now() - timedelta(hours=1),
        current_round=2,
    )

    # Добавляем оценки за 1-й раунд (бой равный)
    add_round_scores(boxing_fight2, side_judge1, 1, 10, 10)
    add_round_scores(boxing_fight2, side_judge2, 1, 9, 10)
    add_round_scores(boxing_fight2, side_judge3, 1, 10, 9)

    # Во 2-м раунде — НОКАУТ! Главный судья останавливает бой
    # БЕЗ учёта оценок боковых судей, назначает победу
    stop_fight_by_head_judge(
        boxing_fight2,
        winner=fighters['boxer2'],
        method='knockout',
        notes='Нокаут во 2-м раунде. Главный судья остановил бой. '
              'Боковые судьи не учитывались — победа присуждена рефери.'
    )

    # --- Бой 3: Бокс — финал, в процессе ---
    boxing_final = create_fight(
        boxing_tournament, boxing_bracket,
        fighters['boxer1'], fighters['boxer2'],
        round_number=2, match_number=1,
        head_judge=head_judge,
        side_judges=[side_judge1, side_judge2, side_judge3],
        status='in_progress',
        start_time=timezone.now() - timedelta(minutes=10),
        is_final=True,
    )

    print(f"✅ Бокс: создано {Fight.objects.filter(tournament=boxing_tournament).count()} боёв")

    # =============================================================================
    # САМБО
    # =============================================================================
    print("\n" + "=" * 60)
    print("🤼 СОЗДАЁМ ТУРНИР ПО БОЕВОМУ САМБО")
    print("=" * 60)

    sambo_tournament = create_tournament(
        'Тестовый турнир по самбо "Бурый медведь"',
        sport_type='sambo',
        location='Санкт-Петербург, Дворец спорта'
    )
    sambo_bracket = create_bracket(sambo_tournament, size=4)

    # --- Бой 1: Самбо — болевой приём ---
    sambo_fight1 = create_fight(
        sambo_tournament, sambo_bracket,
        fighters['sambo1'], fighters['sambo3'],
        round_number=1, match_number=1,
        head_judge=referee,
        status='completed',
        start_time=timezone.now() - timedelta(hours=3),
        total_rounds=1,
        round_duration=300,
    )
    stop_fight_by_head_judge(
        sambo_fight1,
        winner=fighters['sambo1'],
        method='submission',
        notes='Болевой приём на руку в 2-й минуте. Боец сдался.'
    )

    # --- Бой 2: Самбо — технический нокаут (бросок) ---
    sambo_fight2 = create_fight(
        sambo_tournament, sambo_bracket,
        fighters['sambo2'], fighters['sambo4'],
        round_number=1, match_number=2,
        head_judge=referee,
        status='completed',
        start_time=timezone.now() - timedelta(hours=2),
        total_rounds=1,
        round_duration=300,
    )
    stop_fight_by_head_judge(
        sambo_fight2,
        winner=fighters['sambo2'],
        method='technical_knockout',
        notes='Тотальный бросок через спину. Соперник не смог продолжать.'
    )

    # --- Бой 3: Самбо — дисквалификация ---
    sambo_fight3 = create_fight(
        sambo_tournament, sambo_bracket,
        fighters['sambo1'], fighters['sambo2'],
        round_number=2, match_number=1,
        head_judge=referee,
        status='completed',
        start_time=timezone.now() - timedelta(hours=1),
        total_rounds=1,
        round_duration=300,
    )
    stop_fight_by_head_judge(
        sambo_fight3,
        winner=fighters['sambo1'],
        method='disqualification',
        notes='Запрещённый приём (удар коленом в голову). Дисквалификация.'
    )

    # --- Бой 4: Самбо — техническая победа (walkover) ---
    sambo_fight4 = create_fight(
        sambo_tournament, sambo_bracket,
        fighters['sambo3'], fighters['sambo4'],
        round_number=2, match_number=2,
        head_judge=referee,
        status='completed',
        start_time=timezone.now() - timedelta(minutes=30),
        total_rounds=1,
        round_duration=300,
    )
    stop_fight_by_head_judge(
        sambo_fight4,
        winner=fighters['sambo4'],
        method='walkover',
        notes='Соперник не вышел на бой. Техническая победа.'
    )

    # --- Бой 5: Самбо — финал, в процессе ---
    sambo_final = create_fight(
        sambo_tournament, sambo_bracket,
        fighters['sambo1'], fighters['sambo4'],
        round_number=3, match_number=1,
        head_judge=referee,
        status='in_progress',
        start_time=timezone.now() - timedelta(minutes=5),
        is_final=True,
        total_rounds=1,
        round_duration=300,
    )

    print(f"✅ Самбо: создано {Fight.objects.filter(tournament=sambo_tournament).count()} боёв")

    # =============================================================================
    # ИТОГИ
    # =============================================================================
    print("\n" + "=" * 60)
    print("🎉 ТЕСТОВЫЕ ДАННЫЕ УСПЕШНО ЗАГРУЖЕНЫ!")
    print("=" * 60)

    print("\n📋 УЧЁТНЫЕ ДАННЫЕ:")
    print("   admin          / admin123     (суперпользователь)")
    print("   head_judge     / judge123     (главный судья)")
    print("   side_judge1-3  / judge123     (боковые судьи)")
    print("   referee        / judge123     (рефери самбо)")
    print("   boxer1-4       / fighter123   (боксёры)")
    print("   sambo1-4       / fighter123   (самбисты)")

    print("\n🏆 ТУРНИРЫ:")
    print(f"   🥊 {boxing_tournament.name}")
    print(f"   🤼 {sambo_tournament.name}")

    print("\n📊 СТАТИСТИКА БОЁВ:")
    total_fights = Fight.objects.count()
    completed = Fight.objects.filter(status='completed').count()
    in_progress = Fight.objects.filter(status='in_progress').count()
    print(f"   Всего боёв:      {total_fights}")
    print(f"   Завершённых:     {completed}")
    print(f"   В процессе:      {in_progress}")

    print("\n🥊 БОКС — способы побед:")
    for method, label in Fight._meta.get_field('win_method').choices:
        count = Fight.objects.filter(tournament=boxing_tournament, win_method=method).count()
        if count:
            print(f"   • {label}: {count}")

    print("\n🤼 САМБО — способы побед:")
    for method, label in Fight._meta.get_field('win_method').choices:
        count = Fight.objects.filter(tournament=sambo_tournament, win_method=method).count()
        if count:
            print(f"   • {label}: {count}")

    print("\n📝 ОСОБЫЕ СЛУЧАИ:")
    print("   • Бокс Fight #2: Нокаут — главный судья остановил бой")
    print("     без учёта оценок боковых судей")
    print("   • Самбо Fight #3: Дисквалификация за запрещённый приём")
    print("   • Самбо Fight #4: Техническая победа (неявка соперника)")

    print("\n" + "=" * 60)


# =============================================================================
# ЗАПУСК
# =============================================================================

if __name__ == '__main__':
    create_test_data()