from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


# === НОВАЯ МОДЕЛЬ ДЛЯ КОММЕРЧЕСКОГО ИСПОЛЬЗОВАНИЯ ===
class Federation(models.Model):
    """Модель для продажи лицензий федерациям"""
    name = models.CharField(max_length=200, verbose_name='Название федерации')
    description = models.TextField(blank=True, null=True, verbose_name='Описание')

    # НОВОЕ ПОЛЕ:
    sports = models.CharField(
        max_length=255, blank=True, null=True, verbose_name='Виды спорта',
        help_text="Хранится как строка через запятую (например: boxing,mma,sambo)"
    )

    # Поля для лицензирования
    is_active = models.BooleanField(default=True, verbose_name='Лицензия активна')
    valid_until = models.DateField(null=True, blank=True, verbose_name='Лицензия действует до')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')

    class Meta:
        verbose_name = 'Федерация (Лицензия)'
        verbose_name_plural = 'Федерации (Лицензии)'

    def __str__(self):
        return self.name


class Profile(models.Model):
    # ТВОИ СТАРЫЕ ROLE_CHOICES ОСТАЛИСЬ БЕЗ ИЗМЕНЕНИЙ
    ROLE_CHOICES = (
        ('system_admin', 'Администратор системы'),
        ('tournament_admin', 'Администратор соревнований'),
        ('judge', 'Судья'),
        ('coach', 'Тренер'),
        ('fighter', 'Участник'),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='fighter')

    # НОВОЕ ПОЛЕ: Привязка к федерации
    federation = models.ForeignKey(
        Federation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='profiles',
        verbose_name='Федерация'
    )
    club = models.CharField(max_length=150, blank=True, null=True, verbose_name='Клуб (для тренера/бойца)')

    class Meta:
        verbose_name = 'Профиль'
        verbose_name_plural = 'Профили'

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"

    @property
    def actual_role(self):
        """
        Актуальная роль с учётом связанных объектов.
        Используется в шаблонах, когда поле role могло ещё не синхронизироваться.
        """
        user = self.user
        if user.is_superuser:
            return 'system_admin'
        if self.role in ('system_admin', 'tournament_admin'):
            return self.role
        if hasattr(user, 'judge') and user.judge.is_active:
            return 'judge'
        if hasattr(user, 'fighter'):
            return 'fighter'
        return self.role or 'fighter'

    def get_actual_role_display(self):
        return dict(self.ROLE_CHOICES).get(self.actual_role, 'Не определена')


# ТВОИ СИГНАЛЫ ОСТАЛИСЬ БЕЗ ИЗМЕНЕНИЙ
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()