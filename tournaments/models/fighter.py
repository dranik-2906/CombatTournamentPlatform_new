from datetime import date
from django.db import models
from django.db.models import Q
from django.contrib.auth.models import User
from ..validators import validate_birth_date, validate_weight


class Fighter(models.Model):
    GENDER_CHOICES = (('M', 'Мужской'), ('F', 'Женский'))

    user = models.OneToOneField(
        User, on_delete=models.CASCADE,
        related_name='fighter', verbose_name='Пользователь'
    )
    first_name = models.CharField(max_length=100, verbose_name='Имя')
    last_name = models.CharField(max_length=100, verbose_name='Фамилия')

    # ВАЛИДАЦИЯ ДАТЫ
    date_of_birth = models.DateField(validators=[validate_birth_date], verbose_name='Дата рождения')
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, verbose_name='Пол')

    # ИСПРАВЛЕНИЕ: DecimalField вместо FloatField и добавление валидатора
    weight = models.DecimalField(
        max_digits=5, decimal_places=2,
        validators=[validate_weight],
        verbose_name='Вес (кг)'
    )

    club = models.CharField(max_length=200, verbose_name='Клуб')
    coach = models.CharField(max_length=200, verbose_name='Тренер')
    photo = models.ImageField(upload_to='fighters', blank=True, null=True, verbose_name='Фото')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Боец'
        verbose_name_plural = 'Бойцы'
        ordering = ['last_name', 'first_name']

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def age(self):
        if not self.date_of_birth:
            return None
        today = date.today()
        return today.year - self.date_of_birth.year - (
                (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )

    @property
    def birth_year(self):
        return self.date_of_birth.year if self.date_of_birth else None

    def get_stats(self):
        # ИСПРАВЛЕНИЕ: Локальный импорт Fight, чтобы избежать циклического импорта
        from .fight import Fight

        fights = Fight.objects.filter(Q(fighter1=self) | Q(fighter2=self), status='completed')
        total = fights.count()
        wins = fights.filter(winner=self).count()
        draws = fights.filter(is_draw=True).count()
        losses = total - wins - draws

        return {
            'total_fights': total,
            'wins': wins,
            'losses': losses,
            'draws': draws
        }