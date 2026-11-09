import logging
import math
import random
from django.db import transaction
from django.contrib.auth.models import User
from ..models import Bracket, BracketNode, Fight, Match, TournamentRegistration, TimerSettings

logger = logging.getLogger('tournaments')


class BracketService:
    """Сервис для генерации и управления турнирными сетками"""

    @staticmethod
    def _get_fight_defaults(bracket):
        """Получить настройки таймера для боёв в сетке"""
        defaults = {
            'total_rounds': 3,
            'round_duration': 180,
            'break_duration': 60,
        }
        try:
            ts, _ = TimerSettings.objects.get_or_create(
                tournament=bracket.tournament,
                defaults=defaults
            )
            defaults['total_rounds'] = ts.number_of_rounds
            defaults['round_duration'] = ts.round_duration
            defaults['break_duration'] = ts.break_duration
        except Exception:
            pass
        return defaults

    import random
    from ..models import Fight

    def generate_single_elimination(bracket, participants):
        """
        Генерирует полную олимпийскую сетку.
        Создаёт матчи для всех раундов, включая финал.
        """
        # 1. Перемешиваем участников (если нужен случайный посев)
        participants = list(participants)
        random.shuffle(participants)

        # 2. Определяем количество раундов
        # Ближайшая степень двойки вверх
        num_participants = len(participants)
        total_rounds = 1
        while (2 ** total_rounds) < num_participants:
            total_rounds += 1

        bracket.total_rounds = total_rounds
        bracket.current_round = 1
        bracket.save()

        # 3. Создаём пустые матчи для ВСЕХ раундов
        for round_num in range(1, total_rounds + 1):
            matches_in_round = 2 ** (total_rounds - round_num)

            for match_num in range(1, matches_in_round + 1):
                Fight.objects.create(
                    tournament=bracket.tournament,
                    bracket=bracket,
                    round_number=round_num,
                    match_number=match_num,
                    status='scheduled',
                )

        # НОВОЕ: Создаем бой за 3-е место (если включено)
        if bracket.has_bronze_match:
            Fight.objects.create(
                tournament=bracket.tournament,
                bracket=bracket,
                round_number=total_rounds,  # Визуально можно привязать к финальному раунду
                match_number=99,  # Уникальный номер, чтобы не пересекался с финалом
                status='scheduled',
                is_bronze_match=True
            )

        # 4. Заполняем первый раунд реальными участниками
        first_round_fights = Fight.objects.filter(
            bracket=bracket,
            round_number=1
        ).order_by('match_number')

        # Распределяем участников по парам
        for i, fight in enumerate(first_round_fights):
            # Берём двух участников для каждого матча
            fighter1_index = i * 2
            fighter2_index = i * 2 + 1

            if fighter1_index < len(participants):
                fight.fighter1 = participants[fighter1_index]
            if fighter2_index < len(participants):
                fight.fighter2 = participants[fighter2_index]

            # Если один из участников отсутствует (BYE),
            # то второй автоматически проходит дальше
            if fight.fighter1 and not fight.fighter2:
                fight.winner = fight.fighter1
                fight.status = 'completed'
            elif fight.fighter2 and not fight.fighter1:
                fight.winner = fight.fighter2
                fight.status = 'completed'

            fight.save()

        return True, f'Сетка успешно сгенерирована. Раундов: {total_rounds}'

    @staticmethod
    @transaction.atomic
    def generate_round_robin(bracket, participants):
        """Генерация круговой системы с разделением на туры"""
        participants = list(participants)
        random.shuffle(participants)

        # Если нечетное количество, добавляем "пустого" игрока для BYE
        if len(participants) % 2 != 0:
            participants.append(None)

        n = len(participants)
        rounds = n - 1
        matches_per_round = n // 2

        bracket.total_rounds = rounds
        bracket.current_round = 1
        bracket.save()

        fight_defaults = BracketService._get_fight_defaults(bracket)

        # Алгоритм круглого стола
        for r in range(rounds):
            match_num = 1
            for i in range(matches_per_round):
                p1 = participants[i]
                p2 = participants[n - 1 - i]

                if p1 is not None and p2 is not None:
                    Fight.objects.create(
                        tournament=bracket.tournament,
                        bracket=bracket,
                        age_weight_category=bracket.age_weight_category,
                        round_number=r + 1,
                        match_number=match_num,
                        fighter1=p1,
                        fighter2=p2,
                        status='scheduled',
                        **fight_defaults
                    )
                elif p1 is not None or p2 is not None:
                    # Автопроход (BYE)
                    Fight.objects.create(
                        tournament=bracket.tournament,
                        bracket=bracket,
                        age_weight_category=bracket.age_weight_category,
                        round_number=r + 1,
                        match_number=match_num,
                        fighter1=p1 if p1 else p2,
                        fighter2=None,
                        status='completed',
                        winner=p1 if p1 else p2,
                        **fight_defaults
                    )
                match_num += 1

            # Ротация участников (первый остается на месте, остальные сдвигаются)
            participants = [participants[0]] + [participants[-1]] + participants[1:-1]

        return True, f'Круговая система сгенерирована. Туров: {rounds}'

    @staticmethod
    @transaction.atomic
    def generate_mixed(bracket, participants):
        """Смешанная система: групповой этап (round 1) + плей-офф (round >= 2)"""
        try:
            if not participants or len(participants) < 3:
                return False, "Недостаточно участников для смешанной системы (минимум 3)"

            Fight.objects.filter(bracket=bracket).delete()
            Match.objects.filter(bracket=bracket).delete()

            participants_list = list(participants)
            random.shuffle(participants_list)

            fight_defaults = BracketService._get_fight_defaults(bracket)

            match_number = 1
            for i in range(len(participants_list)):
                for j in range(i + 1, len(participants_list)):
                    Fight.objects.create(
                        tournament=bracket.tournament,
                        bracket=bracket,
                        age_weight_category=bracket.age_weight_category,
                        fighter1=participants_list[i].fighter,
                        fighter2=participants_list[j].fighter,
                        round_number=1,  # Групповой этап
                        match_number=match_number,
                        status='scheduled',
                        **fight_defaults
                    )
                    match_number += 1

            bracket.size = len(participants_list)
            bracket.total_rounds = 2  # Группа + плей-офф
            bracket.current_round = 1
            bracket.is_generated = True
            bracket.status = 'generated'
            bracket.save()

            return True, f"Смешанная система: {len(participants_list)} участников, групповой этап создан"

        except Exception as e:
            logger.error(f"Ошибка смешанной системы: {e}", exc_info=True)
            return False, f"Ошибка: {str(e)}"

    @staticmethod
    @transaction.atomic
    def advance_winners(bracket):
        """Продвижение победителей в следующий раунд"""
        logger.info(f"=== advance_winners: сетка #{bracket.id}, раунд {bracket.current_round} ===")
        try:
            current_round = bracket.current_round

            # Берем все бои текущего раунда, КРОМЕ боя за 3-е место
            fights_in_round = Fight.objects.filter(
                bracket=bracket,
                round_number=current_round,
                is_bronze_match=False
            )
            total = fights_in_round.count()
            completed_regular = fights_in_round.filter(status='completed')
            bye_fights = fights_in_round.filter(fighter2__isnull=True)
            effectively_completed = completed_regular.count() + bye_fights.count()

            logger.info(
                f"Раунд {current_round}: всего {total}, завершено {completed_regular.count()}, BYE {bye_fights.count()}")

            if effectively_completed < total:
                return False, f"Не все бои раунда {current_round} завершены (готово {effectively_completed} из {total})"

            # === КРУГОВАЯ СИСТЕМА ===
            if bracket.bracket_type == 'round_robin':
                from ..services import FightService
                standings = FightService.get_standings(bracket)
                if standings and len(standings) > 0:
                    winner = standings[0]['fighter']
                    bracket.complete(winner)
                    return True, f"Круговая система завершена. Победитель: {winner}"
                return False, "Нет данных для определения победителя"

            # === СМЕШАННАЯ СИСТЕМА ===
            if bracket.bracket_type == 'mixed' and current_round == 1:
                from ..services import FightService
                success, msg = FightService.create_playoff_from_round_robin(bracket)
                if success:
                    bracket.current_round = 2
                    bracket.save()
                    return True, f"Плей-офф создан: {msg}"
                return False, msg

            # === ОЛИМПИЙСКАЯ СИСТЕМА (и плей-офф смешанной) ===
            winners = []
            for f in fights_in_round.order_by('match_number'):
                if f.fighter2 is None:
                    if f.fighter1:
                        winners.append(f.fighter1)
                elif f.status == 'completed' and f.winner:
                    winners.append(f.winner)

            if not winners:
                return False, "Нет победителей для продвижения"

            if len(winners) == 1:
                bracket.complete(winners[0])
                return True, f"Турнир завершён! Победитель: {winners[0]}"

            next_round = current_round + 1
            next_fights_count = len(winners) // 2
            bye_exists = len(winners) % 2 == 1

            # Очищаем следующий раунд перед созданием новых боёв (кроме бронзового)
            Fight.objects.filter(
                bracket=bracket,
                round_number=next_round,
                is_bronze_match=False
            ).delete()

            fight_defaults = BracketService._get_fight_defaults(bracket)
            match_counter = 1

            # ========================================================
            # НОВАЯ ЛОГИКА: Создание боя за 3-е место (Бронзовый финал)
            # ========================================================
            # Если осталось 2 победителя (это финал), и в сетке включена опция бронзы
            if len(winners) == 2 and getattr(bracket, 'has_bronze_match', False):
                # Проверяем, не создан ли уже бой за 3-е место
                bronze_exists = Fight.objects.filter(bracket=bracket, is_bronze_match=True).exists()
                if not bronze_exists:
                    # Собираем проигравших в полуфиналах (текущий раунд)
                    losers = []
                    for f in completed_regular:
                        if f.fighter1 and f.fighter2:  # Исключаем BYE
                            loser = f.fighter2 if f.winner == f.fighter1 else f.fighter1
                            losers.append(loser)

                    # Если набралось ровно 2 проигравших, создаем бой
                    if len(losers) == 2:
                        bronze_fight = Fight.objects.create(
                            tournament=bracket.tournament,
                            bracket=bracket,
                            age_weight_category=bracket.age_weight_category,
                            round_number=next_round,
                            match_number=99,  # Специальный номер для бронзы
                            status='scheduled',
                            is_bronze_match=True,
                            **fight_defaults
                        )
                        bronze_fight.fighter1 = losers[0]
                        bronze_fight.fighter2 = losers[1]
                        bronze_fight.save(update_fields=['fighter1', 'fighter2'])
                        logger.info(f"Создан бой за 3-е место: {losers[0]} vs {losers[1]}")

            # ========================================================

            # Создаем обычные бои следующего раунда (включая финал)
            for i in range(next_fights_count):
                f1 = winners[i * 2]
                f2 = winners[i * 2 + 1]
                fight = Fight.objects.create(
                    tournament=bracket.tournament,
                    bracket=bracket,
                    age_weight_category=bracket.age_weight_category,
                    round_number=next_round,
                    match_number=match_counter,
                    status='scheduled',
                    is_final=(len(winners) == 2),
                    **fight_defaults
                )
                fight.fighter1 = f1
                fight.fighter2 = f2
                fight.save(update_fields=['fighter1', 'fighter2'])
                match_counter += 1

            if bye_exists:
                f_bye = winners[-1]
                fight = Fight.objects.create(
                    tournament=bracket.tournament,
                    bracket=bracket,
                    age_weight_category=bracket.age_weight_category,
                    round_number=next_round,
                    match_number=match_counter,
                    status='scheduled',
                    **fight_defaults
                )
                fight.fighter1 = f_bye
                fight.fighter2 = None
                fight.save(update_fields=['fighter1', 'fighter2'])

            bracket.current_round = next_round
            if next_round >= bracket.total_rounds:
                bracket.status = 'in_progress'
            bracket.save()

            return True, f"Раунд {next_round} создан"

        except Exception as e:
            logger.error(f"Ошибка продвижения: {e}", exc_info=True)
            return False, f"Ошибка: {str(e)}"
    @staticmethod
    def check_completion(bracket):
        """Проверить завершённость сетки"""
        if bracket.status == 'completed':
            return True
        fights = Fight.objects.filter(bracket=bracket)
        total = fights.count()
        completed = fights.filter(status='completed').count()
        if total > 0 and total == completed:
            final = fights.filter(round_number=bracket.total_rounds, status='completed').first()
            if final and final.winner:
                bracket.complete(final.winner)
                return True
        return False

    @staticmethod
    def get_standings(bracket):
        """Подсчёт очков и мест для круговой системы"""
        fights = Fight.objects.filter(bracket=bracket, status='completed')
        stats = {}

        def init_stat(fighter):
            if fighter.id not in stats:
                stats[fighter.id] = {
                    'fighter': fighter, 'wins': 0, 'draws': 0, 'losses': 0,
                    'points': 0, 'score_diff': 0, 'place': None
                }
            return stats[fighter.id]

        for f in fights:
            if not f.fighter1 or not f.fighter2:
                continue

            s1 = init_stat(f.fighter1)
            s2 = init_stat(f.fighter2)

            # Разница очков
            s1['score_diff'] += (f.score_fighter1 - f.score_fighter2)
            s2['score_diff'] += (f.score_fighter2 - f.score_fighter1)

            if f.is_draw:
                s1['draws'] += 1;
                s1['points'] += 1
                s2['draws'] += 1;
                s2['points'] += 1
            elif f.winner == f.fighter1:
                s1['wins'] += 1;
                s1['points'] += 3
                s2['losses'] += 1
            elif f.winner == f.fighter2:
                s2['wins'] += 1;
                s2['points'] += 3
                s1['losses'] += 1

        # Сортировка: по очкам, затем по разнице очков
        sorted_stats = sorted(stats.values(), key=lambda x: (x['points'], x['score_diff']), reverse=True)

        # Присвоение мест
        for idx, s in enumerate(sorted_stats):
            s['place'] = idx + 1
            s['club'] = s['fighter'].club if hasattr(s['fighter'], 'club') else '—'
            s['method'] = f"{s['wins']} побед"  # Для вывода в призерах

        return sorted_stats