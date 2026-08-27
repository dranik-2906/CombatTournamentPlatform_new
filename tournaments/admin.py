from django.contrib import admin
from .models import (
    Tournament, AgeGroup, WeightCategory, AgeWeightCategory,
    Fighter, Judge, Bracket, BracketNode, Fight, Match,
    TimerSettings, TournamentRegistration,
    TournamentCheckpoint, RegistrationCheckpoint,
)


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = ['name', 'start_date', 'end_date', 'location', 'is_active', 'status_display']
    list_filter = ['is_active', 'sport_type', 'start_date']
    search_fields = ['name', 'location']
    date_hierarchy = 'start_date'


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


@admin.register(Bracket)
class BracketAdmin(admin.ModelAdmin):
    list_display = ['name', 'tournament', 'bracket_type', 'status', 'size', 'current_round', 'winner']
    list_filter = ['status', 'bracket_type', 'tournament']


@admin.register(Fight)
class FightAdmin(admin.ModelAdmin):
    list_display = ['id', 'tournament', 'fighter1', 'fighter2', 'winner', 'status', 'round_number', 'judge']
    list_filter = ['status', 'tournament']
    search_fields = ['fighter1__first_name', 'fighter2__first_name']


@admin.register(TournamentRegistration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ['fighter', 'tournament', 'age_weight_category', 'is_approved', 'completion_percent']
    list_filter = ['is_approved', 'tournament']
    search_fields = ['fighter__first_name', 'fighter__last_name']


@admin.register(TournamentCheckpoint)
class TournamentCheckpointAdmin(admin.ModelAdmin):
    list_display = ['tournament', 'name', 'code', 'order', 'is_required']
    list_filter = ['tournament', 'is_required']
    search_fields = ['name']


@admin.register(RegistrationCheckpoint)
class RegistrationCheckpointAdmin(admin.ModelAdmin):
    list_display = ['registration', 'checkpoint', 'is_checked']
    list_filter = ['is_checked', 'checkpoint__tournament']
    search_fields = ['registration__fighter__first_name', 'checkpoint__name']


admin.site.register(AgeGroup)
admin.site.register(WeightCategory)
admin.site.register(AgeWeightCategory)
admin.site.register(BracketNode)
admin.site.register(Match)
admin.site.register(TimerSettings)