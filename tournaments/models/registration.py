from django.db import models
from .tournament import Tournament
from .fighter import Fighter
from .category import AgeGroup, WeightCategory, AgeWeightCategory


class TournamentRegistration(models.Model):
    tournament = models.ForeignKey(
        Tournament, on_delete=models.CASCADE,
        related_name='registrations', verbose_name='Турнир'
    )
    fighter = models.ForeignKey(
        Fighter, on_delete=models.CASCADE,
        related_name='registrations', verbose_name='Боец'
    )
    age_group = models.ForeignKey(
        AgeGroup, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='Возрастная группа'
    )
    weight_category = models.ForeignKey(
        WeightCategory, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='Весовая категория'
    )
    age_weight_category = models.ForeignKey(
        AgeWeightCategory, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='registrations',
        verbose_name='Возрастно-весовая категория'
    )

    is_approved = models.BooleanField(default=False, verbose_name='Допущен к турниру')

    # Final result
    final_place = models.PositiveIntegerField(null=True, blank=True, verbose_name='Итоговое место')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Регистрация на турнир'
        verbose_name_plural = 'Регистрации на турниры'
        unique_together = ('tournament', 'fighter')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.fighter} - {self.tournament}"

    @property
    def all_checks_passed(self):
        """Все обязательные чекпоинты пройдены"""
        required = self.tournament.checkpoints.filter(is_required=True)
        if not required.exists():
            return True
        passed = self.checkpoint_statuses.filter(checkpoint__in=required, is_checked=True).count()
        return passed == required.count()

    @property
    def completion_percent(self):
        checkpoints = self.tournament.checkpoints.all()
        if not checkpoints.exists():
            return 100
        total = checkpoints.count()
        passed = self.checkpoint_statuses.filter(is_checked=True).count()
        return int(passed / total * 100)

    def approve(self):
        if self.all_checks_passed:
            self.is_approved = True
            self.save(update_fields=['is_approved', 'updated_at'])
            return True
        return False


class TournamentCheckpoint(models.Model):
    tournament = models.ForeignKey(
        Tournament, on_delete=models.CASCADE,
        related_name='checkpoints', verbose_name='Турнир'
    )
    name = models.CharField('Название', max_length=100)
    code = models.CharField('Код (1 буква)', max_length=10, blank=True, help_text='Например: В, Д, О')
    order = models.PositiveIntegerField('Порядок', default=0)
    is_required = models.BooleanField('Обязательный', default=True)

    class Meta:
        ordering = ['order']
        unique_together = ['tournament', 'name']
        verbose_name = 'Чекпоинт турнира'
        verbose_name_plural = 'Чекпоинты турнира'

    def __str__(self):
        return f"{self.tournament.name} — {self.name}"


class RegistrationCheckpoint(models.Model):
    registration = models.ForeignKey(
        TournamentRegistration, on_delete=models.CASCADE,
        related_name='checkpoint_statuses', verbose_name='Регистрация'
    )
    checkpoint = models.ForeignKey(
        TournamentCheckpoint, on_delete=models.CASCADE,
        verbose_name='Чекпоинт'
    )
    is_checked = models.BooleanField('Пройден', default=False)

    class Meta:
        unique_together = ['registration', 'checkpoint']
        verbose_name = 'Статус чекпоинта'
        verbose_name_plural = 'Статусы чекпоинтов'

    def __str__(self):
        return f"{self.registration.fighter} — {self.checkpoint.name}: {'Да' if self.is_checked else 'Нет'}"


# Сигналы
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=Tournament)
def create_default_checkpoints(sender, instance, created, **kwargs):
    """При создании турнира автоматически добавляем 3 базовых чекпоинта"""
    if created and not instance.checkpoints.exists():
        defaults = [
            {'name': 'Взвешивание', 'code': 'В', 'order': 1},
            {'name': 'Документы', 'code': 'Д', 'order': 2},
            {'name': 'Оплата', 'code': 'О', 'order': 3},
        ]
        for d in defaults:
            TournamentCheckpoint.objects.get_or_create(
                tournament=instance, name=d['name'], defaults=d
            )


@receiver(post_save, sender=TournamentRegistration)
def create_registration_checkpoints(sender, instance, created, **kwargs):
    """При создании регистрации создаём статусы для всех чекпоинтов турнира"""
    if created:
        for cp in instance.tournament.checkpoints.all():
            RegistrationCheckpoint.objects.get_or_create(
                registration=instance, checkpoint=cp, defaults={'is_checked': False}
            )


class Registration:
    pass