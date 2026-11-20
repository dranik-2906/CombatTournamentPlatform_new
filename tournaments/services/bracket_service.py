import logging
import math
import random
from django.db import transaction
from django.db.models import F, Max
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

        # Настройки таймера, чтобы создаваемые бои имели те же поля,
        # что и в других генераторах (round_robin, mixed).
        fight_defaults = BracketService._get_fight_defaults(bracket)

        # 3. Создаём пустые матчи для ВСЕХ раундов
        for round_num in range(1, total_rounds + 1):
            matches_in_round = 2 ** (total_rounds - round_num)

            for match_num in range(1, matches_in_round + 1):
                Fight.objects.create(
                    tournament=bracket.tournament,
                    bracket=bracket,
                    age_weight_category=bracket.age_weight_category,
                    round_number=round_num,
                    match_number=match_num,
                    status='scheduled',
                    **fight_defaults
                )

        # Бой за 3-е место (если включено)
        if getattr(bracket, 'has_bronze_match', False):
            Fight.objects.create(
                tournament=bracket.tournament,
                bracket=bracket,
                age_weight_category=bracket.age_weight_category,
                round_number=total_rounds,
                match_number=99,
                status='scheduled',
                is_bronze_match=True,
                **fight_defaults
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
            elif not fight.fighter1 and not fight.fighter2:
                # ─── ИСПРАВЛЕНИЕ 3.1 ───
                # Полностью пустой бой (оба участника None) возникает,
                # когда число участников не является степенью двойки.
                # Помечаем его завершённым, иначе advance_winners навсегда
                # заблокирует раунд: бой висит в статусе 'scheduled',
                # но не может быть завершён (некому драться).
                fight.status = 'completed'

            fight.save()

        # ─── ИСПРАВЛЕНИЕ 2.5 ───
        bracket.is_generated = True
        bracket.size = len(participants)
        bracket.status = 'generated'
        bracket.save(update_fields=['is_generated', 'size', 'status'])

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

        # ─── ИСПРАВЛЕНИЕ 2.5 ───
        bracket.is_generated = True
        bracket.size = len([p for p in participants if p is not None])
        bracket.status = 'generated'
        bracket.save(update_fields=['is_generated', 'size', 'status'])

        return True, f'Круговая система сгенерирована. Туров: {rounds}'

    @staticmethod
    @transaction.atomic
    def generate_mixed(bracket, participants):
        """Смешанная система: разделение на подгруппы А и Б (круговая) + плей-офф"""
        try:
            if not participants or len(participants) < 4:
                return False, "Недостаточно участников для смешанной системы (минимум 4)"

            # Очищаем старые бои перед генерацией
            Fight.objects.filter(bracket=bracket).delete()

            participants_list = []
            for p in participants:
                # Если передали регистрации, достаем самих бойцов
                participants_list.append(p.fighter if hasattr(p, 'fighter') else p)

            import random
            random.shuffle(participants_list)

            # Делим участников на две группы (поровну или с перевесом в 1 человека)
            mid = len(participants_list) // 2
            if len(participants_list) % 2 != 0:
                mid += 1  # Первая группа получает на 1 больше

            group_a = participants_list[:mid]
            group_b = participants_list[mid:]

            fight_defaults = BracketService._get_fight_defaults(bracket)

            # Генерируем бои для Группы А
            match_number = 1
            for i in range(len(group_a)):
                for j in range(i + 1, len(group_a)):
                    Fight.objects.update_or_create(
                        tournament=bracket.tournament,
                        bracket=bracket,
                        round_number=1,
                        match_number=match_number,
                        defaults={
                            'age_weight_category': bracket.age_weight_category,
                            'fighter1': group_a[i],
                            'fighter2': group_a[j],
                            'group_name': 'A',
                            'status': 'scheduled',
                            **fight_defaults
                        }
                    )
                    match_number += 1

            # Генерируем бои для Группы Б
            # ВАЖНО: match_number для группы Б должен отличаться от группы А,
            # иначе update_or_create перезапишет бои группы А. Используем offset 1000.
            match_number = 1000
            for i in range(len(group_b)):
                for j in range(i + 1, len(group_b)):
                    Fight.objects.update_or_create(
                        tournament=bracket.tournament,
                        bracket=bracket,
                        round_number=1,
                        match_number=match_number,
                        defaults={
                            'age_weight_category': bracket.age_weight_category,
                            'fighter1': group_b[i],
                            'fighter2': group_b[j],
                            'group_name': 'B',
                            'status': 'scheduled',
                            **fight_defaults
                        }
                    )
                    match_number += 1

            bracket.size = len(participants_list)
            bracket.total_rounds = 1
            bracket.current_round = 1
            bracket.is_generated = True
            bracket.status = 'generated'
            bracket.save()

            return True, f"Смешанная система: {len(group_a)} чел. в Группе А, {len(group_b)} чел. в Группе Б"

        except Exception as e:
            logger.error(f"Ошибка смешанной системы: {e}", exc_info=True)
            # ─── КРИТИЧНО: без этого @transaction.atomic закоммитит
            # частичные изменения (удаление старых боёв без создания новых).
            transaction.set_rollback(True)
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

            # Явная проверка каждого боя, без двойного учёта BYE.
            # Бой «готов», если:
            #   1) status='completed' (обычный бой с результатом ИЛИ пустой бой,
            #      помеченный completed в generate_single_elimination);
            #   2) это корректный BYE: есть fighter1, нет fighter2, winner == fighter1.
            unfinished_fights = fights_in_round.exclude(
                status='completed'
            ).exclude(
                fighter1__isnull=False,
                fighter2__isnull=True,
                winner=F('fighter1'),
            )

            unfinished_count = unfinished_fights.count()
            if unfinished_count > 0:
                ready_count = total - unfinished_count
                logger.info(
                    f"Раунд {current_round}: всего {total}, готово {ready_count}, "
                    f"не завершено {unfinished_count}")
                # Возврат без изменений в БД — откат не нужен.
                return False, (
                    f"Не все бои раунда {current_round} завершены "
                    f"(готово {ready_count} из {total})"
                )

            logger.info(f"Раунд {current_round}: все {total} боёв завершены (включая BYE)")

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
                    # Обновляем раунды после создания плей-офф
                    max_round = Fight.objects.filter(bracket=bracket).aggregate(
                        max_r=Max('round_number')
                    )['max_r'] or 1
                    bracket.current_round = max_round
                    bracket.total_rounds = max_round
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
            # Бронзовый финал (заполняем заранее созданный бой)
            # ========================================================
            if len(winners) == 2 and getattr(bracket, 'has_bronze_match', False):
                losers = []
                for f in completed_regular:
                    if f.fighter1 and f.fighter2:  # Исключаем BYE и пустые бои
                        loser = f.fighter2 if f.winner == f.fighter1 else f.fighter1
                        losers.append(loser)

                if len(losers) == 2:
                    # ─── ИСПРАВЛЕНИЕ 3.2 ───
                    # Бронзовый бой уже создан заранее в generate_single_elimination
                    # (round_number=total_rounds, match_number=99, is_bronze_match=True).
                    # Раньше код проверял bronze_exists и ПРОПУСКАЛ заполнение,
                    # из-за чего бой навсегда оставался пустым. Теперь мы его
                    # находим (или создаём, если по какой-то причине нет) и
                    # ЗАПОЛНЯЕМ участниками.
                    bronze_fight = Fight.objects.filter(
                        bracket=bracket, is_bronze_match=True
                    ).first()

                    if bronze_fight is None:
                        bronze_fight = Fight.objects.create(
                            tournament=bracket.tournament,
                            bracket=bracket,
                            age_weight_category=bracket.age_weight_category,
                            round_number=next_round,
                            match_number=99,
                            status='scheduled',
                            is_bronze_match=True,
                            **fight_defaults
                        )

                    bronze_fight.fighter1 = losers[0]
                    bronze_fight.fighter2 = losers[1]
                    bronze_fight.save(update_fields=['fighter1', 'fighter2'])
                    logger.info(f"Создан бой за 3-е место: {losers[0]} vs {losers[1]}")

            # ========================================================
            # Обычные бои следующего раунда (включая финал)
            # ========================================================
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

            # BYE в следующем раунде — сразу завершённый,
            # иначе при следующем вызове advance_winners() он не пройдёт
            # валидацию (status='scheduled', winner=None) и раунд «застрянет».
            if bye_exists:
                f_bye = winners[-1]
                Fight.objects.create(
                    tournament=bracket.tournament,
                    bracket=bracket,
                    age_weight_category=bracket.age_weight_category,
                    round_number=next_round,
                    match_number=match_counter,
                    status='completed',
                    winner=f_bye,
                    fighter1=f_bye,
                    fighter2=None,
                    **fight_defaults
                )

            bracket.current_round = next_round
            if next_round >= bracket.total_rounds:
                bracket.status = 'in_progress'
            bracket.save()

            return True, f"Раунд {next_round} создан"

        except Exception as e:
            logger.error(f"Ошибка продвижения: {e}", exc_info=True)
            # ─── КРИТИЧНО: иначе частичное создание боёв / заполнение
            # бронзы закоммитится.
            transaction.set_rollback(True)
            return False, f"Ошибка: {str(e)}"

    @staticmethod
    def check_completion(bracket):
        """Проверить завершённость сетки (бронза не влияет на победителя турнира)"""
        if bracket.status == 'completed':
            return True

        # ─── ИСПРАВЛЕНИЕ 3.3 ───
        # Бронзовый бой исключён из подсчёта завершённости: он может
        # доигрываться отдельно (а при 3 участниках — вообще не создаётся,
        # потому что проигравших в полуфиналах только один). Раньше
        # пустая бронза со status='scheduled' навсегда блокировала
        # завершение сетки.
        fights = Fight.objects.filter(bracket=bracket, is_bronze_match=False)
        total = fights.count()
        completed = fights.filter(status='completed').count()
        if total > 0 and total == completed:
            final = fights.filter(
                round_number=bracket.total_rounds,
                status='completed',
                is_bronze_match=False,
            ).first()
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
                s1['draws'] += 1
                s1['points'] += 1
                s2['draws'] += 1
                s2['points'] += 1
            elif f.winner == f.fighter1:
                s1['wins'] += 1
                s1['points'] += 3
                s2['losses'] += 1
            elif f.winner == f.fighter2:
                s2['wins'] += 1
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