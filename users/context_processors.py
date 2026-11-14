def user_role(request):
    """
    Добавляет в контекст шаблона объект user_role и строку role.
    Приоритет ролей: Судья > Администратор > Организатор > Тренер > Участник > Пользователь
    """
    if not request.user.is_authenticated:
        return {'user_role': None, 'role': 'guest'}

    # --- СУДЬЯ (два источника: profile.role и модель Judge) ---
    is_judge = False
    if hasattr(request.user, 'profile') and request.user.profile:
        if request.user.profile.role == 'judge':
            is_judge = True

    if not is_judge:
        try:
            if hasattr(request.user, 'judge') and request.user.judge and request.user.judge.is_active:
                is_judge = True
        except Exception:
            pass

    if is_judge:
        return {
            'user_role': {
                'label': 'Судья',
                'badge_class': 'bg-info',
                'text_class': 'text-white',
                'icon': 'fa-gavel',
            },
            'role': 'judge'  # <-- ДОБАВЛЕНО
        }

    # --- АДМИНИСТРАТОР ---
    if request.user.is_superuser:
        return {
            'user_role': {
                'label': 'Администратор',
                'badge_class': 'bg-danger',
                'text_class': 'text-white',
                'icon': 'fa-user-shield',
            },
            'role': 'system_admin'  # <-- ДОБАВЛЕНО
        }

    # --- ОСТАЛЬНЫЕ РОЛИ ИЗ ПРОФИЛЯ ---
    role_str = ''
    if hasattr(request.user, 'profile') and request.user.profile:
        role_str = request.user.profile.role

    roles_map = {
        'system_admin': {
            'label': 'Администратор',
            'badge_class': 'bg-danger',
            'text_class': 'text-white',
            'icon': 'fa-user-shield',
        },
        'tournament_admin': {
            'label': 'Организатор',
            'badge_class': 'bg-warning',
            'text_class': 'text-dark',
            'icon': 'fa-user-tie',
        },
        'coach': {
            'label': 'Тренер',
            'badge_class': 'bg-info',
            'text_class': 'text-dark',
            'icon': 'fa-chalkboard-teacher',
        },
        'fighter': {
            'label': 'Участник',
            'badge_class': 'bg-success',
            'text_class': 'text-white',
            'icon': 'fa-user',
        },
    }

    if role_str in roles_map:
        return {
            'user_role': roles_map[role_str],
            'role': role_str  # <-- ДОБАВЛЕНО
        }

    return {
        'user_role': {
            'label': 'Пользователь',
            'badge_class': 'bg-secondary',
            'text_class': 'text-white',
            'icon': 'fa-user',
        },
        'role': 'guest'  # <-- ДОБАВЛЕНО
    }