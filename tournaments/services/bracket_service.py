import logging
import math
import random
from django.db import transaction
from django.contrib.auth.models import User
from ..models import Bracket, BracketNode, Fight, Match, TournamentRegistration

logger = logging.getLogger('tournaments')


class BracketService:
    """Сервис для генерации и управления турнирными сетками"""

    @staticmethod
    @transaction.atomic
    def generate_single_elimination(bracket, participants):
        """
        Генерация олимпийской системы с динамическим числом BYE.
        При нечётном числе участников создаётся один BYE в первом раунде.
        """
        try:
            if not participants or len(participants) < 2:
                return False, "Недостаточно участников (минимум 2)"

            # Очистка старых данных
            Fight.objects.filter(bracket=bracket).delete()
            Match.objects.filter(bracket=bracket).delete()

            num = len(participants)
            participants_list = list(participants)
            random.shuffle(participants_list)

            total_rounds = math.ceil(math.log2(num))
            round_number = 1
            match_counter = 1

            # Создаём пары
            pairs = num // 2
            bye_exists = num % 2 == 1

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
                    is_final=(num == 2)
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
                    is_final=(num == 1)
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

            logger.info(f"Сетка #{bracket.id}: {num} участников, {total_rounds} раундов, BYE в 1-м раунде: {bye_exists}")
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
                        status='scheduled'
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
        """Смешанная система: групповой этап + плей-офф"""
        try:
            if not participants or len(participants) < 3:
                return False, "Недостаточно участников для смешанной системы (минимум 3)"

            Fight.objects.filter(bracket=bracket).delete()
            Match.objects.filter(bracket=bracket).delete()

            participants_list = list(participants)
            random.shuffle(participants_list)

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
                        status='scheduled'
                    )
                    match_number += 1

            bracket.size = len(participants_list)
            bracket.total_rounds = 2
            bracket.current_round = 1
            bracket.is_generated = True
            bracket.status = 'generated'
            bracket.save()

            return True, f"Смешанная система: {len(participants_list)} участников, групповой этап + плей-офф"

        except Exception as e:
            logger.error(f"Ошибка смешанной системы: {e}", exc_info=True)
            return False, f"Ошибка: {str(e)}"

    @staticmethod
    @transaction.atomic
    def advance_winners(bracket):
        """
        Продвижение победителей в следующий раунд с динамическим числом BYE.
        """
        logger.info(f"=== advance_winners: сетка #{bracket.id}, текущий раунд {bracket.current_round} ===")
        try:
            current_round = bracket.current_round

            # Проверяем, что все бои текущего раунда завершены (или BYE)
            fights_in_round = Fight.objects.filter(bracket=bracket, round_number=current_round)
            total = fights_in_round.count()
            completed_regular = fights_in_round.filter(status='completed')
            bye_fights = fights_in_round.filter(fighter2__isnull=True)
            effectively_completed = completed_regular.count() + bye_fights.count()

            logger.info(f"Раунд {current_round}: всего {total}, завершено {completed_regular.count()}, BYE {bye_fights.count()}, итого {effectively_completed}")

            if effectively_completed < total:
                return False, f"Не все бои раунда {current_round} завершены (готово {effectively_completed} из {total})"

            next_round = current_round + 1

            # Если круговая система — нет продвижения
            if bracket.bracket_type == 'round_robin':
                return False, "Круговая система не предполагает продвижение"

            # Смешанная система — обрабатываем отдельно (оставляем как есть, так как не используется)
            if bracket.bracket_type == 'mixed' and current_round == 1:
                # Здесь можно вызвать отдельный метод, но для простоты пропускаем
                pass

            # ОЛИМПИЙСКАЯ СИСТЕМА
            # Собираем победителей
            winners = []
            for f in fights_in_round.order_by('match_number'):
                if f.fighter2 is None:
                    if f.fighter1:
                        winners.append(f.fighter1)
                        logger.info(f"  BYE-бой #{f.id}: победитель {f.fighter1}")
                elif f.status == 'completed' and f.winner:
                    winners.append(f.winner)
                    logger.info(f"  Бой #{f.id}: победитель {f.winner}")
                else:
                    logger.warning(f"  Бой #{f.id} не готов: статус {f.status}, winner {f.winner}")

            if not winners:
                return False, "Нет победителей для продвижения"

            logger.info(f"Всего победителей: {len(winners)}")

            if len(winners) == 1:
                bracket.complete(winners[0])
                return True, f"Турнир завершён! Победитель: {winners[0]}"

            # Создаём следующий раунд
            next_fights_count = len(winners) // 2
            bye_exists = len(winners) % 2 == 1

            # Удаляем старые бои следующего раунда (если есть)
            Fight.objects.filter(bracket=bracket, round_number=next_round).delete()

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
                    is_final=(len(winners) == 2)
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
                    is_final=(len(winners) == 1)
                )
                fight.fighter1 = f_bye
                fight.fighter2 = None
                fight.save(update_fields=['fighter1', 'fighter2'])

            # Обновляем сетку
            bracket.current_round = next_round
            if next_round >= bracket.total_rounds:
                bracket.status = 'in_progress'
            bracket.save()

            logger.info(f"Создан раунд {next_round} с {next_fights_count} парами и {1 if bye_exists else 0} BYE")
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
    def _get_or_create_dummy_fighter():
        """УСТАРЕВШЕЕ — не используется"""
        from ..models import Fighter
        user, _ = User.objects.get_or_create(
            username='__dummy__bye__',
            defaults={
                'first_name': 'BYE',
                'last_name': 'SYSTEM',
                'email': 'bye@system.local',
                'is_active': False,
            }
        )
        dummy, _ = Fighter.objects.get_or_create(
            user=user,
            defaults={
                'first_name': 'BYE',
                'last_name': 'AUTOMATIC',
                'date_of_birth': '2000-01-01',
                'gender': 'M',
                'weight': 0,
                'club': 'System',
                'coach': 'System'
            }
        )