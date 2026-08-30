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

    @staticmethod
    @transaction.atomic
    def generate_single_elimination(bracket, participants):
        """
        Генерация олимпийской системы с динамическим числом BYE.
        """
        try:
            if not participants or len(participants) < 2:
                return False, "Недостаточно участников (минимум 2)"

            Fight.objects.filter(bracket=bracket).delete()
            Match.objects.filter(bracket=bracket).delete()

            num = len(participants)
            participants_list = list(participants)
            random.shuffle(participants_list)

            total_rounds = math.ceil(math.log2(num))
            round_number = 1
            match_counter = 1

            pairs = num // 2
            bye_exists = num % 2 == 1

            fight_defaults = BracketService._get_fight_defaults(bracket)

            for i in range(pairs):
                p1 = participants_list[i * 2]
                p2 = participants_list[i * 2 + 1]
                fight = Fight.objects.create(
                    tournament=bracket.tournament,
                    bracket=bracket,
                    age_weight_category=bracket.age_weight_category,
                    round_number=round_number,
                    match_number=match_counter,
                    status='scheduled',
                    is_final=(num == 2),
                    **fight_defaults
                )
                fight.fighter1 = p1.fighter
                fight.fighter2 = p2.fighter
                fight.save(update_fields=['fighter1', 'fighter2'])
                match_counter += 1

            if bye_exists:
                p_bye = participants_list[-1]
                fight = Fight.objects.create(
                    tournament=bracket.tournament,
                    bracket=bracket,
                    age_weight_category=bracket.age_weight_category,
                    round_number=round_number,
                    match_number=match_counter,
                    status='scheduled',
                    is_final=(num == 1),
                    **fight_defaults
                )
                fight.fighter1 = p_bye.fighter
                fight.fighter2 = None
                fight.save(update_fields=['fighter1', 'fighter2'])

            bracket.size = num
            bracket.current_round = 1
            bracket.total_rounds = total_rounds
            bracket.is_generated = True
            bracket.status = 'generated'
            bracket.save()

            logger.info(f"Сетка #{bracket.id}: {num} участников, {total_rounds} раундов, BYE: {bye_exists}")
            return True, f"Олимпийская система: {num} участников, {total_rounds} раундов"

        except Exception as e:
            logger.error(f"Ошибка генерации сетки #{bracket.id}: {e}", exc_info=True)
            return False, f"Ошибка генерации: {str(e)}"

    @staticmethod
    @transaction.atomic
    def generate_round_robin(bracket, participants):
        """Генерация круговой системы"""
        try:
            if not participants or len(participants) < 2:
                return False, "Недостаточно участников"

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
                        round_number=1,
                        match_number=match_number,
                        status='scheduled',
                        **fight_defaults
                    )
                    match_number += 1

            bracket.size = len(participants_list)
            bracket.total_rounds = 1
            bracket.current_round = 1
            bracket.is_generated = True
            bracket.status = 'generated'
            bracket.save()

            return True, f"Круговая система: {len(participants_list)} участников, {match_number - 1} матчей"

        except Exception as e:
            logger.error(f"Ошибка круговой системы: {e}", exc_info=True)
            return False, f"Ошибка: {str(e)}"

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

            fights_in_round = Fight.objects.filter(bracket=bracket, round_number=current_round)
            total = fights_in_round.count()
            completed_regular = fights_in_round.filter(status='completed')
            bye_fights = fights_in_round.filter(fighter2__isnull=True)
            effectively_completed = completed_regular.count() + bye_fights.count()

            logger.info(f"Раунд {current_round}: всего {total}, завершено {completed_regular.count()}, BYE {bye_fights.count()}")

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

            # === ОЛИМПИЙСКАЯ СИСТЕМА ===
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

            Fight.objects.filter(bracket=bracket, round_number=next_round).delete()

            fight_defaults = BracketService._get_fight_defaults(bracket)
            match_counter = 1
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