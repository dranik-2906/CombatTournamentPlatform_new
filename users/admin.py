from django.contrib import admin
from .models import Profile, Federation


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    # Твой старый код + добавлено поле 'federation' в список и фильтры для удобства
    list_display = ['user', 'role', 'federation']
    list_filter = ['role', 'federation']
    search_fields = ['user__username']


# НОВАЯ РЕГИСТРАЦИЯ ДЛЯ ФЕДЕРАЦИЙ
@admin.register(Federation)
class FederationAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'valid_until', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name']