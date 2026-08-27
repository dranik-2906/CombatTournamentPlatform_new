from datetime import date
from django.db import models
from django.contrib.auth.models import User


class Fighter(models.Model):
    GENDER_CHOICES = (('M', 'Мужской'), ('F', 'Женский'))

    user = models.OneToOneField(
        User, on_delete=models.CASCADE,
        related_name='fighter', verbose_name='Пользователь'
    )
    first_name = models.CharField(max_length=100, verbose_name='Имя')
    last_name = models.CharField(max_length=100, verbose_name='Фамилия')
    date_of_birth = models.DateField(verbose_name='Дата рождения')
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, verbose_name='Пол')
    weight = models.FloatField(verbose_name='Вес (кг)')
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
        fights = self.fights_as_fighter1.all() | self.fights_as_fighter2.all()
        total = fights.filter(status='completed').count()
        wins = self.won_fights.count()
        return {'total_fights': total, 'wins': wins, 'losses': total - wins}