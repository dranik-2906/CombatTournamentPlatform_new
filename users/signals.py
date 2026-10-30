from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import Profile


def sync_profile_role(user):
    """
    Синхронизирует Profile.role с фактическим наличием Judge/Fighter.
    Приоритет: system_admin > tournament_admin > judge > fighter.
    """
    if not user or not user.is_authenticated:
        return

    try:
        profile = user.profile
    except Profile.DoesNotExist:
        return

    # Суперпользователь всегда системный администратор
    if user.is_superuser:
        new_role = 'system_admin'
    # Роли, назначенные вручную, не понижаем
    elif profile.role in ('system_admin', 'tournament_admin'):
        new_role = profile.role
    # Активный судья
    elif hasattr(user, 'judge') and user.judge.is_active:
        new_role = 'judge'
    # Участник
    elif hasattr(user, 'fighter'):
        new_role = 'fighter'
    else:
        new_role = 'fighter'

    if profile.role != new_role:
        # update() не вызывает post_save на Profile, поэтому рекурсии не будет
        Profile.objects.filter(pk=profile.pk).update(role=new_role)
        profile.refresh_from_db(fields=['role'])


@receiver(post_save, sender='tournaments.Judge')
def on_judge_save(sender, instance, **kwargs):
    if instance.user_id:
        sync_profile_role(instance.user)


@receiver(post_delete, sender='tournaments.Judge')
def on_judge_delete(sender, instance, **kwargs):
    if instance.user_id:
        sync_profile_role(instance.user)


@receiver(post_save, sender='tournaments.Fighter')
def on_fighter_save(sender, instance, **kwargs):
    if instance.user_id:
        sync_profile_role(instance.user)


@receiver(post_delete, sender='tournaments.Fighter')
def on_fighter_delete(sender, instance, **kwargs):
    if instance.user_id:
        sync_profile_role(instance.user)