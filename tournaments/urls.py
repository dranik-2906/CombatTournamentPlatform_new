from django.urls import path
from . import views

app_name = 'tournaments'

urlpatterns = [
    # Турниры
    path('', views.tournament_list, name='tournament_list'),
    path('<int:pk>/', views.tournament_detail, name='tournament_detail'),
    path('create/', views.create_tournament, name='create_tournament'),
    path('<int:pk>/edit/', views.edit_tournament, name='edit_tournament'),
    path('<int:pk>/delete/', views.delete_tournament, name='delete_tournament'),

    # Регистрация
    path('<int:pk>/register/', views.register_for_tournament, name='register_for_tournament'),
    path('my-registrations/', views.my_registrations, name='my_registrations'),
    path('my-tournaments/', views.my_tournaments, name='my_tournaments'),

    # Категории
    path('<int:tournament_id>/categories/', views.manage_categories, name='manage_categories'),

    # Чекпоинты
    path('<int:tournament_id>/checkpoints/', views.manage_checkpoints, name='manage_checkpoints'),
    path('checkpoint/<int:checkpoint_id>/edit/', views.edit_checkpoint, name='edit_checkpoint'),
    path('checkpoint/<int:checkpoint_id>/delete/', views.delete_checkpoint, name='delete_checkpoint'),

    # Сетки
    path('<int:tournament_id>/brackets/generate/', views.generate_brackets, name='generate_brackets'),
    path('<int:tournament_id>/bracket/<int:bracket_id>/', views.bracket_view, name='bracket_view'),
    path('<int:tournament_id>/bracket/<int:bracket_id>/delete/', views.delete_bracket, name='delete_bracket'),
    path('<int:tournament_id>/brackets/advance/', views.advance_winners_view, name='advance_winners'),

    # Бои
    path('<int:tournament_id>/fights/', views.fights_management, name='fights_management'),
    path('<int:tournament_id>/fight/<int:fight_id>/assign-judge/', views.assign_judge, name='assign_judge'),
    path('<int:tournament_id>/fight/<int:fight_id>/update/', views.admin_update_fight, name='admin_update_fight'),
    path('<int:tournament_id>/fight/<int:fight_id>/delete/', views.delete_fight, name='delete_fight'),
    path('<int:tournament_id>/timer-settings/', views.timer_settings_view, name='timer_settings'),
    path('fight/<int:fight_id>/results/', views.fight_results, name='fight_results'),
    path('<int:tournament_id>/fights/delete-all/', views.delete_all_fights, name='delete_all_fights'),

    # Таймер (для судьи)
    path('<int:tournament_id>/fight/<int:fight_id>/timer/', views.fight_timer, name='fight_timer'),
    path('<int:tournament_id>/fight/<int:fight_id>/timer/control/', views.timer_control, name='timer_control'),
    path('<int:tournament_id>/fight/<int:fight_id>/timer/complete/', views.complete_fight_ajax, name='complete_fight_ajax'),

    # Судьи
    path('judge/dashboard/', views.judge_dashboard, name='judge_dashboard'),
    path('judge/my-fights/', views.judge_my_fights, name='judge_my_fights'),
    path('judge/fight/<int:fight_id>/panel/', views.judge_fight_panel, name='judge_fight_panel'),
    path('judge/fight/<int:tournament_id>/<int:fight_id>/result/', views.judge_update_result, name='judge_update_result'),
    path('judge/fight/<int:tournament_id>/<int:fight_id>/notes/', views.update_judge_notes, name='update_judge_notes'),

    # Управление судьями (админ)
    path('judges/', views.judge_list, name='judge_list'),
    path('judges/add/', views.add_judge, name='add_judge'),
    path('judges/<int:judge_id>/edit/', views.edit_judge, name='edit_judge'),
    path('judges/<int:judge_id>/toggle/', views.toggle_judge_active, name='toggle_judge'),

    # Участники
    path('participants/', views.participants_management, name='participants_management'),
    path('<int:tournament_id>/participants/add/', views.add_participant, name='add_participant'),
    path('<int:tournament_id>/participants/excel/', views.add_participant_excel, name='add_participant_excel'),
    path('<int:tournament_id>/participants/excel/template/', views.download_excel_template, name='download_excel_template'),
    path('registration/<int:registration_id>/update/', views.update_registration, name='update_registration'),
    path('registration/<int:registration_id>/delete/', views.delete_registration, name='delete_registration'),
    path('<int:tournament_id>/auto-assign/', views.auto_assign_categories_view, name='auto_assign'),
    path('fighters/', views.fighter_list, name='fighter_list'),
    path('fighters/<int:pk>/', views.fighter_detail, name='fighter_detail'),
]