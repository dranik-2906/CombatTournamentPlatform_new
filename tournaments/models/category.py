from django.db import models
from .tournament import Tournament, GENDER_CHOICES


class AgeGroup(models.Model):
    name = models.CharField(max_length=100, verbose_name='Название')
    min_age = models.PositiveIntegerField(verbose_name='Минимальный возраст')
    max_age = models.PositiveIntegerField(verbose_name='Максимальный возраст')

    class Meta:
        verbose_name = 'Возрастная группа'
        verbose_name_plural = 'Возрастные группы'

    def __str__(self):
        return f"{self.name} ({self.min_age}-{self.max_age} лет)"


class WeightCategory(models.Model):
    tournament = models.ForeignKey(
        Tournament, on_delete=models.CASCADE,
        related_name='weight_categories', verbose_name='Турнир'
    )
    name = models.CharField(max_length=100, verbose_name='Название')
    min_weight = models.DecimalField(max_digits=5, decimal_places=2, verbose_name='Минимальный вес')
    max_weight = models.DecimalField(max_digits=5, decimal_places=2, verbose_name='Максимальный вес')
    gender = models.CharField(
        max_length=10,
        choices=[('male', 'Мужской'), ('female', 'Женский'), ('both', 'Оба пола')],
        verbose_name='Пол'
    )

    class Meta:
        verbose_name = 'Весовая категория'
        verbose_name_plural = 'Весовые категории'
        unique_together = ['tournament', 'name', 'gender']

    def __str__(self):
        return f"{self.name} ({self.gender})"


class AgeWeightCategory(models.Model):
    BRACKET_SYSTEM_CHOICES = [
        ('single_elimination', 'Олимпийская система'),
        ('round_robin', 'Круговая система'),
        ('mixed', 'Смешанная система'),
    ]

    tournament = models.ForeignKey(
        Tournament, on_delete=models.CASCADE,
        related_name='age_weight_categories', verbose_name='Турнир'
    )
    name = models.CharField(max_length=100, verbose_name='Название категории')
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, verbose_name='Пол')
    min_birth_year = models.PositiveIntegerField(verbose_name='Минимальный год рождения')
    max_birth_year = models.PositiveIntegerField(verbose_name='Максимальный год рождения')
    min_weight = models.DecimalField(max_digits=5, decimal_places=2, verbose_name='Минимальный вес (кг)')
    max_weight = models.DecimalField(max_digits=5, decimal_places=2, verbose_name='Максимальный вес (кг)')
    bracket_system = models.CharField(
        max_length=20, choices=BRACKET_SYSTEM_CHOICES,
        default='single_elimination', verbose_name='Система проведения'
    )

    class Meta:
        verbose_name = 'Возрастно-весовая категория'
        verbose_name_plural = 'Возрастно-весовые категории'
        unique_together = ('tournament', 'name', 'gender')
        ordering = ['gender', 'min_weight']

    def __str__(self):
        return f"{self.name} ({self.get_gender_display()})"

    @property
    def participant_count(self):
        return self.registrations.count()
