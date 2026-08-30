import logging
from django.db import models
from django.db.models import Q
from .tournament import Tournament
from .category import AgeWeightCategory
from .fighter import Fighter
from .judge import Judge
from .bracket import Bracket

logger = logging.getLogger('tournaments')

FIGHT_STATUS = (
    ('scheduled', 'Запланирован'),
    ('in_progress', 'В процессе'),
    ('completed', 'Завершён'),
    ('cancelled', 'Отменён'),
)

WIN_METHODS = (
    ('points', 'По очкам'),
    ('submission', 'Болевой приём'),
    ('knockout', 'Нокаут'),
    ('technical_knockout', 'Технический нокаут'),
    ('disqualification', 'Дисквалификация'),
    ('walkover', 'Техническая победа'),
    ('draw', 'Ничья'),
)


class Match(models.Model):
    """Матч в сетке - связывает две регистрации для турнирной сетки"""
    bracket = models.ForeignKey(
        Bracket, on_delete=models.CASCADE,
        related_name='matches', verbose_name='Сетка'
    )
    round_number = models.PositiveIntegerField(verbose_name='Номер раунда')
    match_number = models.PositiveIntegerField(verbose_name='Номер матча')
    group_number = models.PositiveIntegerField(null=True, blank=True, verbose_name='Номер группы')

    participant1 = models.ForeignKey(
        'TournamentRegistration', on_delete=models.CASCADE,
        null=True, blank=True, related_name='matches_as_p1',
        verbose_name='Участник 1'
    )
    participant2 = models.ForeignKey(
        'TournamentRegistration', on_delete=models.CASCADE,
        null=True, blank=True, related_name='matches_as_p2',
        verbose_name='Участник 2'
    )
    winner = models.ForeignKey(
        'TournamentRegistration', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='won_matches',
        verbose_name='Победитель'
    )
    is_completed = models.BooleanField(default=False, verbose_name='Завершён')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='Завершён в')

    class Meta:
        verbose_name = 'Матч'
        verbose_name_plural = 'Матчи'
        ordering = ['bracket', 'round_number', 'match_number']

    def __str__(self):
        return f"Матч {self.match_number} (Раунд {self.round_number})"


class Fight(models.Model):
    """Бой - реальное событие с результатами и таймером"""
    tournament = models.ForeignKey(
        Tournament, on_delete=models.CASCADE,
        related_name='fights', verbose_name='Турнир'
    )
    bracket = models.ForeignKey(
        Bracket, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='fights',
        verbose_name='Сетка'
    )
    age_weight_category = models.ForeignKey(
        AgeWeightCategory, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='fights',
        verbose_name='Категория'
    )

    fighter1 = models.ForeignKey(
        Fighter, on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='fights_as_fighter1', verbose_name='Боец 1'
    )

    fighter2 = models.ForeignKey(
        Fighter, on_delete=models.CASCADE,
        null=True, blank=True, related_name='fights_as_fighter2',
        verbose_name='Боец 2'
    )
    winner = models.ForeignKey(
        Fighter, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='won_fights',
        verbose_name='Победитель'
    )

    score_fighter1 = models.IntegerField(default=0, verbose_name='Очки бойца 1')
    score_fighter2 = models.IntegerField(default=0, verbose_name='Очки бойца 2')

    status = models.CharField(
        max_length=20, choices=FIGHT_STATUS,
        default='scheduled', verbose_name='Статус'
    )
    start_time = models.DateTimeField(null=True, blank=True, verbose_name='Время начала')
    end_time = models.DateTimeField(null=True, blank=True, verbose_name='Время окончания')

    win_method = models.CharField(
        max_length=50, choices=WIN_METHODS,
        blank=True, verbose_name='Метод победы'
    )
    win_round = models.IntegerField(null=True, blank=True, verbose_name='Раунд победы')
    is_draw = models.BooleanField(default=False, verbose_name='Ничья')

    # === СУДЕЙСТВО ===
    judge = models.ForeignKey(
        Judge, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='fights',
        verbose_name='Судья (общий)'
    )
    head_judge = models.ForeignKey(
        Judge, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='fights_as_head',
        verbose_name='Главный судья'
    )
    side_judges = models.ManyToManyField(
        Judge, blank=True, related_name='fights_as_side',
        verbose_name='Боковые судьи'
    )

    judge_notes = models.TextField(blank=True, verbose_name='Заметки судьи')

    round_number = models.IntegerField(default=1, verbose_name='Номер раунда')
    match_number = models.IntegerField(default=1, verbose_name='Номер матча')
    is_final = models.BooleanField(default=False, verbose_name='Финальный бой')
    next_fight = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='previous_fights',
        verbose_name='Следующий бой'
    )

    # === Timer fields (переопределяемые настройки боя) ===
    total_rounds = models.PositiveIntegerField(default=3, verbose_name='Всего раундов в бою')
    round_duration = models.PositiveIntegerField(default=180, verbose_name='Длительность раунда (сек)')
    break_duration = models.PositiveIntegerField(default=60, verbose_name='Длительность перерыва (сек)')

    current_round = models.PositiveIntegerField(default=1, verbose_name='Текущий раунд')
    round_time_remaining = models.PositiveIntegerField(
        null=True, blank=True, verbose_name='Осталось времени раунда (сек)'
    )
    break_time_remaining = models.PositiveIntegerField(
        null=True, blank=True, verbose_name='Осталось времени перерыва (сек)'
    )
    is_round_running = models.BooleanField(default=False, verbose_name='Раунд идёт')
    is_break_running = models.BooleanField(default=False, verbose_name='Перерыв идёт')
    timer_started_at = models.DateTimeField(
        null=True, blank=True, verbose_name='Таймер запущен'
    )
    last_timer_update = models.DateTimeField(
        null=True, blank=True, verbose_name='Последнее обновление таймера'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Бой'
        verbose_name_plural = 'Бои'
        ordering = ['tournament', 'bracket', 'round_number', 'match_number']
        unique_together = ['tournament', 'bracket', 'round_number', 'match_number']

    def __str__(self):
        if self.fighter1 and self.fighter2:
            return f"Бой #{self.id}: {self.fighter1} vs {self.fighter2}"
        elif self.fighter1:
            return f"Бой #{self.id}: {self.fighter1} (автопроход)"
        return f"Бой #{self.id}"

    def start(self):
        """Начать бой"""
        from django.utils import timezone
        self.status = 'in_progress'
        self.start_time = timezone.now()
        if self.bracket:
            self.bracket.status = 'in_progress'
            self.bracket.save()
        self.save()
        logger.info(f"Бой #{self.id} начат")

    def complete(self, winner=None, method='', notes='', scores=None):
        """Завершить бой"""
        from django.utils import timezone
        self.status = 'completed'
        self.end_time = timezone.now()
        self.winner = winner
        self.win_method = method
        self.judge_notes = notes
        if scores:
            self.score_fighter1 = scores.get('fighter1', 0)
            self.score_fighter2 = scores.get('fighter2', 0)
        self.is_round_running = False
        self.is_break_running = False
        self.save()
        logger.info(f"Бой #{self.id} завершён. Победитель: {winner}, метод: {method}")

    @property
    def is_bye(self):
        """Является ли бой автопроходом"""
        return self.fighter2 is None

    @property
    def loser(self):
        """Вернуть проигравшего"""
        if not self.winner:
            return None
        if self.winner == self.fighter1:
            return self.fighter2
        return self.fighter1

    @property
    def is_boxing_fight(self):
        return self.tournament.is_boxing

    def get_round_scores_summary(self):
        """Возвращает сводку очков по раундам для бокса"""
        if not self.is_boxing_fight:
            return None
        scores = self.round_scores.all()
        if not scores.exists():
            return None

        result = {}
        for rs in scores:
            key = rs.round_number
            if key not in result:
                result[key] = {'f1': 0, 'f2': 0, 'judges': 0}
            result[key]['f1'] += rs.score_fighter1
            result[key]['f2'] += rs.score_fighter2
            result[key]['judges'] += 1
        return result

    def get_total_round_scores(self):
        """Итоговые очки по сумме раундов"""
        summary = self.get_round_scores_summary()
        if not summary:
            return None
        total_f1 = sum(v['f1'] for v in summary.values())
        total_f2 = sum(v['f2'] for v in summary.values())
        return {'fighter1': total_f1, 'fighter2': total_f2}


class RoundScore(models.Model):
    """Оценка бокового судьи за раунд (только для бокса)"""
    fight = models.ForeignKey(
        Fight, on_delete=models.CASCADE,
        related_name='round_scores', verbose_name='Бой'
    )
    judge = models.ForeignKey(
        Judge, on_delete=models.CASCADE,
        related_name='round_scores', verbose_name='Судья'
    )
    round_number = models.PositiveIntegerField(verbose_name='Номер раунда')
    score_fighter1 = models.IntegerField(default=0, verbose_name='Очки боксёра 1')
    score_fighter2 = models.IntegerField(default=0, verbose_name='Очки боксёра 2')

    class Meta:
        verbose_name = 'Оценка за раунд'
        verbose_name_plural = 'Оценки за раунды'
        unique_together = ['fight', 'judge', 'round_number']
        ordering = ['round_number', 'judge__last_name']

    def __str__(self):
        return f"Раунд {self.round_number}: {self.judge} — {self.score_fighter1}:{self.score_fighter2}"