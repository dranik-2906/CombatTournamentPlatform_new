# Combat Tournament Platform

Профессиональная платформа для организации и проведения соревнований по боевым единоборствам.

## Что исправлено и улучшено

### 1. Безопасность
- `SECRET_KEY` вынесен в переменные окружения (`.env`)
- `ALLOWED_HOSTS` больше не перезаписывается пустым списком
- Убраны `@csrf_exempt` с чувствительных endpoint'ов
- Добавлена защита `X_FRAME_OPTIONS`, `SECURE_BROWSER_XSS_FILTER` для production
- `DEBUG=False` по умолчанию для production

### 2. Структура проекта
- Settings разделены на `base.py`, `development.py`, `production.py`
- Модели разбиты на отдельные файлы (`tournament.py`, `fighter.py`, `judge.py`, `bracket.py`, `fight.py`, `timer.py`, `registration.py`, `category.py`)
- Views разбиты на модули (`tournaments.py`, `brackets.py`, `fights.py`, `judges.py`, `participants.py`)
- Бизнес-логика вынесена в `services/` (`BracketService`, `FightService`, `CategoryService`)
- Добавлены Django Forms в `forms.py`
- Убрано дублирование функций (3× `fighter_list`, 2× `auto_assign_categories`)
- Убраны повторяющиеся импорты (8 блоков импортов в одном views.py)

### 3. Модели данных
- Устранено дублирование между `Match` и `Fight` — теперь разные ответственности
- `Fight.save()` больше не содержит автопродвижения (логика в `BracketService`)
- Добавлены `related_name` для всех ForeignKey
- Добавлены индексы (`ordering`, `Meta` опции)
- Добавлены свойства (`all_checks_passed`, `completion_percent`, `full_name`, `age`, `birth_year`)
- Исправлена `unique_together` для `TournamentRegistration`

### 4. Логирование
- Все `print()` заменены на `logging`
- Настроена структурированная конфигурация логов
- Логи пишутся в файл `logs/django.log` и в консоль
- Добавлен `logger` в каждый модуль

### 5. UI/UX
- Обновлён `base.html` — улучшена навигация, добавлены dropdown, badges ролей
- Главная страница — статистика, текущие и ближайшие турниры
- Dashboard — ролевой контент (админ/судья/боец)
- Турнирная сетка — визуальное отображение по раундам
- Все списки с пагинацией
- Адаптивная вёрстка
- Font Awesome 6.5, Bootstrap 5.3

### 6. Декораторы
- Упрощена и исправлена логика `users/decorators.py`
- Убрано автоматическое определение роли по username
- Роль берётся только из `Profile`

### 7. Зависимости
- Заполнен `requirements.txt` со всеми пакетами
- Добавлен `python-dotenv` для переменных окружения

### 8. Тесты
- Добавлены unit-тесты для сервисов
- Добавлены тесты для пользователей
- Добавлены тесты для core

## Установка

```bash
# 1. Клонировать репозиторий
cd combat_platform

# 2. Создать виртуальное окружение
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# 3. Установить зависимости
pip install -r requirements.txt

# 4. Создать .env файл
cp .env.example .env
# Отредактировать .env — установить SECRET_KEY

# 5. Применить миграции
python manage.py migrate

# 6. Создать суперпользователя
python manage.py createsuperuser

# 7. Запустить
python manage.py runserver
```

## Переменные окружения (.env)

```
DJANGO_SECRET_KEY=your-secret-key-here
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
```

## Роли пользователей

| Роль | Код | Доступ |
|------|-----|--------|
| Администратор системы | `system_admin` | Полный доступ |
| Администратор соревнований | `tournament_admin` | Турниры, участники, судьи |
| Судья | `judge` | Панель судьи, таймер |
| Участник | `fighter` | Регистрации, профиль |
