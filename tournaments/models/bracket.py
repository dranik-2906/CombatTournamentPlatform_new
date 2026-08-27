import logging
from django.db import models
from django.utils import timezone
from .tournament import Tournament
from .category import AgeWeightCategory
from .fighter import Fighter

logger = logging.getLogger('tournaments')

BRACKET_TYPES = (
    ('single_elimination', 'Олимпийская система'),
    ('round_robin', 'Круговая система'),
    ('mixed', 'Смешанная система'),
)


class Bracket(models.Model):
    tournament = models.ForeignKey(
        Tournament, on_delete=models.CASCADE,
        related_name='brackets', verbose_name='Турнир'
    )
    name = models.CharField(max_length=200, blank=True, default='', verbose_name='Название сетки')
    description = models.TextField(blank=True, default='', verbose_name='Описание')
    bracket_type = models.CharField(
        max_length=20, choices=BRACKET_TYPES,
        default='single_elimination', verbose_name='Тип сетки'
    )
    age_weight_category = models.ForeignKey(
        AgeWeightCategory, on_delete=models.CASCADE,
        null=True, blank=True, related_name='brackets',
        verbose_name='Возрастно-весовая категория'
    )
    current_round = models.PositiveIntegerField(default=1, verbose_name='Текущий раунд')
    total_rounds = models.PositiveIntegerField(default=0, verbose_name='Всего раундов')
    size = models.PositiveIntegerField(default=0, verbose_name='Количество участников')
    winner = models.ForeignKey(
        Fighter, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='bracket_wins',
        verbose_name='Победитель'
    )
    status = models.CharField(
        max_length=20, default='generated',
        choices=[
            ('generated', 'Сгенерирована'),
            ('in_progress', 'В процессе'),
            ('completed', 'Завершена'),
        ],
        verbose_name='Статус'
    )
    is_generated = models.BooleanField(default=False, verbose_name='Сгенерирована')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='Дата завершения')

    class Meta:
        verbose_name = 'Сетка'
        verbose_name_plural = 'Сетки'
        ordering = ['-created_at']

    def __str__(self):
        if self.name:
            return self.name
        if self.age_weight_category:
            return f"{self.tournament} - {self.age_weight_category.name}"
        return f"{self.tournament} - {self.get_bracket_type_display()}"

    def complete(self, winner):
        """Завершить сетку с указанным победителем"""
        self.winner = winner
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save()
        logger.info(f"Сетка #{self.id} завершена. Победитель: {winner}")


class BracketNode(models.Model):
    bracket = models.ForeignKey(
        Bracket, on_delete=models.CASCADE,
        related_name='nodes', verbose_name='Сетка'
    )
    parent_node = models.ForeignKey(
        'self', on_delete=models.CASCADE,
        null=True, blank=True, related_name='children',
        verbose_name='Родительский узел'
    )
    fighter1 = models.ForeignKey(
        Fighter, on_delete=models.CASCADE,
        null=True, blank=True, related_name='bracket_nodes1',
        verbose_name='Боец 1'
    )
    fighter2 = models.ForeignKey(
        Fighter, on_delete=models.CASCADE,
        null=True, blank=True, related_name='bracket_nodes2',
        verbose_name='Боец 2'
    )
    winner = models.ForeignKey(
        Fighter, on_delete=models.CASCADE,
        null=True, blank=True, related_name='node_wins',
        verbose_name='Победитель'
    )
    round_number = models.PositiveIntegerField(verbose_name='Раунд')
    position = models.PositiveIntegerField(verbose_name='Позиция')

    class Meta:
        verbose_name = 'Узел сетки'
        verbose_name_plural = 'Узлы сетки'
        ordering = ['round_number', 'position']

    def __str__(self):
        if self.fighter1 and self.fighter2:
            return f"Раунд {self.round_number} - {self.fighter1} vs {self.fighter2}"
        return f"Раунд {self.round_number} - Пустой бой"
