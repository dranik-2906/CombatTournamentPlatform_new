import logging
from django.db import models

logger = logging.getLogger('tournaments')

GENDER_CHOICES = (('M', 'Мужской'), ('F', 'Женский'))

SPORT_TYPES = (
    ('boxing', 'Бокс'),
    ('sambo', 'Боевое самбо'),
    ('mma', 'MMA'),
    ('kickboxing', 'Кикбоксинг'),
    ('judo', 'Дзюдо'),
    ('wrestling', 'Вольная борьба'),
    ('other', 'Другое'),
)

BRACKET_TYPES = (
    ('single_elimination', 'Олимпийская система'),
    ('round_robin', 'Круговая система'),
    ('mixed', 'Смешанная система'),
)


class Tournament(models.Model):
    name = models.CharField(max_length=200, verbose_name='Название турнира')
    sport_type = models.CharField(
        max_length=20, choices=SPORT_TYPES, default='sambo',
        verbose_name='Вид спорта'
    )
    start_date = models.DateField(verbose_name='Дата начала')
    end_date = models.DateField(verbose_name='Дата окончания')
    location = models.CharField(max_length=200, verbose_name='Место проведения')
    description = models.TextField(blank=True, verbose_name='Описание')
    bracket_type = models.CharField(
        max_length=20, choices=BRACKET_TYPES, default='single_elimination',
        verbose_name='Тип сетки'
    )
    is_active = models.BooleanField(default=True, verbose_name='Активный')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлён')

    class Meta:
        verbose_name = 'Турнир'
        verbose_name_plural = 'Турниры'
        ordering = ['-start_date']

    def __str__(self):
        return self.name

    @property
    def status_display(self):
        from django.utils import timezone
        today = timezone.now().date()
        if self.end_date < today:
            return 'Завершён'
        elif self.start_date <= today <= self.end_date:
            return 'В процессе'
        return 'Запланирован'

    @property
    def is_boxing(self):
        return self.sport_type == 'boxing'

    @property
    def total_registrations(self):
        return self.registrations.count()

    @property
    def approved_registrations(self):
        return self.registrations.filter(is_approved=True).count()

    @property
    def total_fights(self):
        return self.fights.count()

    @property
    def completed_fights(self):
        return self.fights.filter(status='completed').count()