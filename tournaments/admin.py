from django.contrib import admin
from .models import (
    Tournament, AgeGroup, WeightCategory, AgeWeightCategory,
    Fighter, Judge, Bracket, BracketNode, Fight, Match,
    TimerSettings, TournamentRegistration,
    TournamentCheckpoint, RegistrationCheckpoint,
)
# ИСПОЛЬЗУЕМ get_managed_tournaments ДЛЯ АДМИНКИ
from .permissions import get_managed_tournaments, is_admin


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = ['name', 'start_date', 'end_date', 'location', 'is_active', 'status_display']
    list_filter = ['is_active', 'sport_type', 'start_date']
    search_fields = ['name', 'location']
    date_hierarchy = 'start_date'

    def get_queryset(self, request):
        """Показываем только те турниры, которыми пользователь может управлять"""
        return get_managed_tournaments(request.user)

    def has_add_permission(self, request):
        """Создавать турниры могут только админы и суперюзеры"""
        return is_admin(request.user)

    def has_change_permission(self, request, obj=None):
        """Редактировать можно только управляемые турниры"""
        if not is_admin(request.user):
            return False
        if obj is not None:
            return get_managed_tournaments(request.user).filter(pk=obj.pk).exists()
        return True

    def has_delete_permission(self, request, obj=None):
        """Удалять можно только управляемые турниры"""
        return self.has_change_permission(request, obj)

    def save_model(self, request, obj, form, change):
        """Автоматическая привязка к федерации при создании"""
        if not change and not request.user.is_superuser:
            profile = getattr(request.user, 'profile', None)
            if profile and profile.role == 'tournament_admin' and profile.federation:
                obj.federation = profile.federation
        super().save_model(request, obj, form, change)


@admin.register(Bracket)
class BracketAdmin(admin.ModelAdmin):
    list_display = ['name', 'tournament', 'bracket_type', 'status', 'size', 'current_round', 'winner']
    list_filter = ['status', 'bracket_type', 'tournament']

    def get_queryset(self, request):
        """Скрываем сетки чужих/неуправляемых турниров"""
        qs = super().get_queryset(request)
        return qs.filter(tournament__in=get_managed_tournaments(request.user))


@admin.register(Fight)
class FightAdmin(admin.ModelAdmin):
    list_display = ['id', 'tournament', 'fighter1', 'fighter2', 'winner', 'status', 'round_number', 'judge']
    list_filter = ['status', 'tournament']
    search_fields = ['fighter1__first_name', 'fighter2__first_name']

    def get_queryset(self, request):
        """Скрываем бои чужих/неуправляемых турниров"""
        qs = super().get_queryset(request)
        return qs.filter(tournament__in=get_managed_tournaments(request.user))


@admin.register(TournamentRegistration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ['fighter', 'tournament', 'age_weight_category', 'is_approved', 'completion_percent']
    list_filter = ['is_approved', 'tournament']
    search_fields = ['fighter__first_name', 'fighter__last_name']

    def get_queryset(self, request):
        """Скрываем регистрации на чужие/неуправляемые турниры"""
        qs = super().get_queryset(request)
        return qs.filter(tournament__in=get_managed_tournaments(request.user))


@admin.register(TournamentCheckpoint)
class TournamentCheckpointAdmin(admin.ModelAdmin):
    list_display = ['tournament', 'name', 'code', 'order', 'is_required']
    list_filter = ['tournament', 'is_required']
    search_fields = ['name']

    def get_queryset(self, request):
        """Скрываем чекпоинты чужих/неуправляемых турниров"""
        qs = super().get_queryset(request)
        return qs.filter(tournament__in=get_managed_tournaments(request.user))


@admin.register(RegistrationCheckpoint)
class RegistrationCheckpointAdmin(admin.ModelAdmin):
    list_display = ['registration', 'checkpoint', 'is_checked']
    list_filter = ['is_checked', 'checkpoint__tournament']
    search_fields = ['registration__fighter__first_name', 'checkpoint__name']

    def get_queryset(self, request):
        """Скрываем чекпоинты регистраций на чужие/неуправляемые турниры"""
        qs = super().get_queryset(request)
        return qs.filter(checkpoint__tournament__in=get_managed_tournaments(request.user))


@admin.register(Fighter)
class FighterAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'club', 'weight', 'gender', 'age', 'user']
    list_filter = ['gender', 'club']
    search_fields = ['first_name', 'last_name', 'club']


@admin.register(Judge)
class JudgeAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'category', 'judge_type', 'is_active', 'license_number']
    list_filter = ['is_active', 'category', 'judge_type']
    search_fields = ['first_name', 'last_name']


# Стандартная регистрация без кастомизации (оставлена как было)
admin.site.register(AgeGroup)
admin.site.register(WeightCategory)
admin.site.register(AgeWeightCategory)
admin.site.register(BracketNode)
admin.site.register(Match)
admin.site.register(TimerSettings)