from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from .tournament import Tournament


class TimerSettings(models.Model):
    ROUND_DURATION_CHOICES = [
        (120, '2 минуты'),
        (180, '3 минуты'),
        (300, '5 минуты'),
    ]
    BREAK_DURATION_CHOICES = [
        (30, '30 секунд'),
        (60, '1 минута'),
        (90, '1.5 минуты'),
    ]

    tournament = models.OneToOneField(
        Tournament, on_delete=models.CASCADE,
        related_name='timer_settings', verbose_name='Турнир'
    )
    round_duration = models.PositiveIntegerField(
        choices=ROUND_DURATION_CHOICES, default=180,
        verbose_name='Длительность раунда (сек)'
    )
    break_duration = models.PositiveIntegerField(
        choices=BREAK_DURATION_CHOICES, default=60,
        verbose_name='Длительность перерыва (сек)'
    )
    number_of_rounds = models.PositiveIntegerField(
        default=3, validators=[MinValueValidator(1), MaxValueValidator(10)],
        verbose_name='Количество раундов'
    )
    warning_sound = models.BooleanField(default=True, verbose_name='Звуковое предупреждение')
    final_warning = models.PositiveIntegerField(
        default=10, verbose_name='Финальное предупреждение (сек до конца)'
    )

    class Meta:
        verbose_name = 'Настройки таймера'
        verbose_name_plural = 'Настройки таймеров'

    def __str__(self):
        return f"Таймер: {self.tournament.name}"
