import os
import django
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'combat_platform.settings')
django.setup()

from tournaments.models.tournament import Tournament
from tournaments.models.fighter import Fighter
from tournaments.models.judge import Judge
from tournaments.models.bracket import Bracket
from tournaments.models.fight import Fight

try:
    from users.models import Profile
except ImportError:
    Profile = None

User = get_user_model()

def create_test_data():
    print("🚀 Начинаем создание тестовых данных...")

    # --- 1. Пользователи ---
    admin, _ = User.objects.get_or_create(
        username='admin',
        defaults={'email': 'admin@test.com', 'is_superuser': True, 'is_staff': True}
    )
    admin.set_password('admin123')
    admin.save()

    judge_user, _ = User.objects.get_or_create(
        username='judge',
        defaults={'email': 'judge@test.com'}
    )
    judge_user.set_password('judge123')
    judge_user.save()
    if Profile:
        Profile.objects.get_or_create(user=judge_user, defaults={'role': 'judge'})

    judge, _ = Judge.objects.get_or_create(
        user=judge_user,
        defaults={
            'first_name': 'Иван',
            'last_name': 'Судьин',
            'category': '1',
            'license_number': 'LIC-001',
            'is_active': True,
            'judge_type': 'main',
            'experience_years': 5,
        }
    )

    # Создаём бойцов с пользователями
    fighter_data = [
        ('fighter', 'fighter123', 'Петр', 'Бойцов', 75.5, 'Боевой клуб', 'Тренер Иванов', 25),
        ('fighter2', 'fighter123', 'Алексей', 'Молотов', 80.0, 'Спартак', '', 22),
        ('fighter3', 'fighter123', 'Сергей', 'Кузнецов', 70.0, 'Динамо', '', 28),
        ('fighter4', 'fighter123', 'Андрей', 'Смирнов', 85.0, 'Локомотив', '', 30),
    ]
    fighters = []
    for username, password, first_name, last_name, weight, club, coach, age in fighter_data:
        user, _ = User.objects.get_or_create(username=username, defaults={'email': f'{username}@test.com'})
        user.set_password(password)
        user.save()
        if Profile:
            Profile.objects.get_or_create(user=user, defaults={'role': 'fighter'})
        fighter, _ = Fighter.objects.get_or_create(
            user=user,
            defaults={
                'first_name': first_name,
                'last_name': last_name,
                'date_of_birth': timezone.now().date() - timedelta(days=365*age),
                'weight': weight,
                'club': club,
                'coach': coach,
                'gender': 'M',
            }
        )
        fighters.append(fighter)

    fighter, fighter2, fighter3, fighter4 = fighters

    print("✅ Пользователи и бойцы созданы")

    # --- 2. Турнир ---
    tournament, _ = Tournament.objects.get_or_create(
        name='Тестовый турнир "Золотой пояс"',
        defaults={
            'description': 'Турнир для проверки работы платформы',
            'start_date': timezone.now().date() - timedelta(days=1),
            'end_date': timezone.now().date() + timedelta(days=2),
            'location': 'Москва, Дворец спорта',
            'is_active': True,
            'sport_type': 'boxing',
            'bracket_type': 'single_elimination',
        }
    )

    # --- 3. Сетка (без категорий, просто общая) ---
    bracket, _ = Bracket.objects.get_or_create(
        tournament=tournament,
        # age_weight_category можно не указывать, если поле необязательное
        defaults={
            'bracket_type': 'single_elimination',
            'size': 4,
            'current_round': 1,
            'total_rounds': 2,
            'status': 'in_progress',
        }
    )

    # --- 4. Бои ---
    fight1, _ = Fight.objects.get_or_create(
        bracket=bracket,
        round_number=1,
        match_number=1,
        defaults={
            'tournament': tournament,
            'fighter1': fighter,
            'fighter2': fighter3,
            'status': 'completed',
            'winner': fighter,
            'score_fighter1': 10,
            'score_fighter2': 8,
            'win_method': 'points',
            'judge': judge,
            'start_time': timezone.now() - timedelta(hours=1),
            'end_time': timezone.now() - timedelta(minutes=30),
        }
    )
    fight2, _ = Fight.objects.get_or_create(
        bracket=bracket,
        round_number=1,
        match_number=2,
        defaults={
            'tournament': tournament,
            'fighter1': fighter2,
            'fighter2': fighter4,
            'status': 'completed',
            'winner': fighter2,
            'score_fighter1': 12,
            'score_fighter2': 6,
            'win_method': 'knockout',
            'judge': judge,
            'start_time': timezone.now() - timedelta(hours=2),
            'end_time': timezone.now() - timedelta(hours=1.5),
        }
    )
    fight3, _ = Fight.objects.get_or_create(
        bracket=bracket,
        round_number=2,
        match_number=1,
        defaults={
            'tournament': tournament,
            'fighter1': fighter,
            'fighter2': fighter2,
            'status': 'in_progress',
            'judge': judge,
            'start_time': timezone.now() - timedelta(minutes=10),
        }
    )

    print("✅ Бои созданы")
    print("🎉 Тестовые данные успешно загружены!")
    print(f"Пользователи: admin (пароль admin123), judge (judge123), fighter, fighter2, fighter3, fighter4 (пароль fighter123)")
    print(f"Турнир: {tournament.name}")
    print(f"Активные бои: {Fight.objects.filter(status='in_progress').count()}")
    print(f"Завершённых боёв: {Fight.objects.filter(status='completed').count()}")

if __name__ == '__main__':
    create_test_data()