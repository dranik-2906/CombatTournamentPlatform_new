"""
Единственный источник истины по ролям пользователей.
"""

ROLE_SYSTEM_ADMIN = 'system_admin'
ROLE_TOURNAMENT_ADMIN = 'tournament_admin'
ROLE_JUDGE = 'judge'
ROLE_COACH = 'coach'
ROLE_FIGHTER = 'fighter'

ROLE_CHOICES = (
    (ROLE_SYSTEM_ADMIN, 'Администратор системы'),
    (ROLE_TOURNAMENT_ADMIN, 'Администратор соревнований'),
    (ROLE_JUDGE, 'Судья'),
    (ROLE_COACH, 'Тренер'),
    (ROLE_FIGHTER, 'Участник'),
)

ADMIN_ROLES = {ROLE_SYSTEM_ADMIN, ROLE_TOURNAMENT_ADMIN}

_DISPLAY_PRIORITY = (
    ROLE_SYSTEM_ADMIN,
    ROLE_TOURNAMENT_ADMIN,
    ROLE_JUDGE,
    ROLE_COACH,
    ROLE_FIGHTER,
)

def _profile(user):
    if not user.is_authenticated:
        return None
    return getattr(user, 'profile', None)

def is_system_admin(user):
    profile = _profile(user)
    return bool(user.is_authenticated and (user.is_superuser or (profile and profile.role == ROLE_SYSTEM_ADMIN)))

def is_tournament_admin(user):
    profile = _profile(user)
    return bool(user.is_authenticated and (user.is_superuser or (profile and profile.role in ADMIN_ROLES)))

def is_judge(user):
    profile = _profile(user)
    has_active_judge = hasattr(user, 'judge') and user.judge.is_active
    return bool(user.is_authenticated and (user.is_superuser or has_active_judge or (profile and profile.role == ROLE_JUDGE)))

def is_coach(user):
    profile = _profile(user)
    # ИСПРАВЛЕНИЕ: Убрана мертвая ветка hasattr(user, 'coach'), так как модели Coach не существует
    return bool(user.is_authenticated and profile and profile.role == ROLE_COACH)

def is_fighter(user):
    return bool(user.is_authenticated and hasattr(user, 'fighter'))

def get_user_roles(user):
    if not user.is_authenticated:
        return set()
    roles = set()
    if is_system_admin(user): roles.add(ROLE_SYSTEM_ADMIN)
    if is_tournament_admin(user): roles.add(ROLE_TOURNAMENT_ADMIN)
    if is_judge(user): roles.add(ROLE_JUDGE)
    if is_coach(user): roles.add(ROLE_COACH)
    if is_fighter(user): roles.add(ROLE_FIGHTER)
    return roles

def get_user_role(user):
    if not user.is_authenticated:
        return 'guest'
    roles = get_user_roles(user)
    for role in _DISPLAY_PRIORITY:
        if role in roles:
            return role
    return 'guest'