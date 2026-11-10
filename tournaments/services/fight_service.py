import logging
import math
from django.db import models
from django.utils import timezone
from ..models import Fight, RoundScore
from django.db import models, transaction

logger = logging.getLogger('tournaments')


class FightService:
    @staticmethod
    def get_fights_by_round(bracket):
        """Группировка боёв по раундам"""
        fights = bracket.fights.all().order_by('round_number', 'match_number')
        result = {}
        for f in fights:
            result.setdefault(f.round_number, []).append(f)
        return result

    @staticmethod
    def get_standings(bracket):
        """Подсчёт очков и мест для круговой системы"""
        fights = Fight.objects.filter(bracket=bracket, status='completed')
        stats = {}

        def init_stat(fighter):
            if fighter.id not in stats:
                stats[fighter.id] = {
                    'fighter': fighter,
                    'wins': 0,
                    'draws': 0,
                    'losses': 0,
                    'points': 0,
                    'score_diff': 0,
                    'place': None
                }
            return stats[fighter.id]

        for f in fights:
            if not f.fighter1 or not f.fighter2:
                continue

            s1 = init_stat(f.fighter1)
            s2 = init_stat(f.fighter2)

            # Разница очков (для тай-брейка)
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

        # Сортировка: по очкам (убывание), затем по разнице очков (убывание)
        sorted_stats = sorted(stats.values(), key=lambda x: (x['points'], x['score_diff']), reverse=True)

        # Присвоение мест
        for idx, s in enumerate(sorted_stats):
            s['place'] = idx + 1

        return sorted_stats

    # ==================== УПРАВЛЕНИЕ БОЯМИ ====================

    @staticmethod
    def assign_judge(fight, judge, assign_to_category=False):
        """Назначить судью на бой (и опционально на все бои категории)"""
        fight.judge = judge
        fight.save(update_fields=['judge'])

        if assign_to_category and fight.age_weight_category:
            assigned = Fight.objects.filter(
                tournament=fight.tournament,
                age_weight_category=fight.age_weight_category,
                judge__isnull=True
            ).update(judge=judge)
            return True, f"Судья назначен на бой и ещё {assigned} боёв категории"
        return True, "Судья назначен на бой"

    @staticmethod
    def assign_boxing_judges(fight, head_judge, side_judges_list):
        """Назначить главного и боковых судей для бокса"""
        fight.head_judge = head_judge
        fight.save(update_fields=['head_judge'])
        fight.side_judges.set(side_judges_list)
        return True, f"Назначены: главный {head_judge}, боковые: {len(side_judges_list)}"

    @staticmethod
    def start_fight(fight):
        """Начать бой"""
        fight.status = 'in_progress'
        fight.start_time = timezone.now()
        fight.save(update_fields=['status', 'start_time'])
        return True, "Бой начат"

    @staticmethod
    def complete_fight(fight, winner=None, method='', notes='', scores=None):
        """Завершить бой и продвинуть победителя"""
        fight.status = 'completed'
        fight.end_time = timezone.now()
        fight.winner = winner
        fight.win_method = method
        fight.judge_notes = notes
        if scores:
            fight.score_fighter1 = scores.get('fighter1', 0)
            fight.score_fighter2 = scores.get('fighter2', 0)
        fight.save()

        if fight.is_final and fight.bracket:
            fight.bracket.status = 'completed'
            fight.bracket.winner = winner if winner else None
            fight.bracket.save()

        if fight.next_fight and winner:
            if not fight.next_fight.fighter1:
                fight.next_fight.fighter1 = winner
            elif not fight.next_fight.fighter2:
                fight.next_fight.fighter2 = winner
            fight.next_fight.save()

        return True, "Бой завершён"

    @staticmethod
    def submit_round_score(fight, judge, round_number, score_f1, score_f2):
        """Сохранить оценку бокового судьи за раунд"""
        rs, created = RoundScore.objects.update_or_create(
            fight=fight,
            judge=judge,
            round_number=round_number,
            defaults={
                'score_fighter1': score_f1,
                'score_fighter2': score_f2,
            }
        )
        return True, f"Оценка за раунд {round_number} сохранена"

    @staticmethod
    @transaction.atomic
    def create_playoff_from_round_robin(bracket, advancing_count=None):
        """Создать перекрестный плей-офф (А1 vs Б2, Б1 vs А2)"""
        from django.db import models, transaction
        from ..models import Fight, Bracket
        from .bracket_service import BracketService

        try:
            # === БЛОКИРУЕМ СЕТКУ, чтобы избежать двойного создания при быстрых кликах ===
            bracket = Bracket.objects.select_for_update().get(pk=bracket.pk)

            # 1. Получаем бои группового этапа отдельно для каждой группы
            group_a_fights = bracket.fights.filter(round_number=1, group_name='A')
            group_b_fights = bracket.fights.filter(round_number=1, group_name='B')

            # 2. СЧИТАЕМ ОЧКИ ЧЕРЕЗ ЕДИНУЮ ФУНКЦИЮ (ту же, что используется для отрисовки таблицы)
            # ВАЖНО: Убедись, что в _round_robin_standings добавлен параметр fights_queryset!
            standings_a = FightService._round_robin_standings(bracket, fights_queryset=group_a_fights)
            standings_b = FightService._round_robin_standings(bracket, fights_queryset=group_b_fights)

            # Берем топ-2 из каждой группы
            top_a = [s['fighter'] for s in standings_a[:2]]
            top_b = [s['fighter'] for s in standings_b[:2]]

            # Заполняем пустоты, если в группе меньше 2 человек
            while len(top_a) < 2: top_a.append(None)
            while len(top_b) < 2: top_b.append(None)

            # 3. Формируем полуфиналы (А1 vs Б2, Б1 vs А2)
            semi_finals_pairs = [
                (top_a[0], top_b[1]),  # А1 vs Б2
                (top_b[0], top_a[1])   # Б1 vs А2
            ]

            # 4. Удаляем старые бои плей-офф (все, что больше 1 раунда) для очистки
            Fight.objects.filter(bracket=bracket, round_number__gt=1).delete()

            playoff_round = 2  # Плей-офф всегда начинается со 2-го раунда

            try:
                fight_defaults = BracketService._get_fight_defaults(bracket)
            except Exception:
                fight_defaults = {}

            current_fights = []
            match_num = 1

            # 5. Создаем полуфиналы
            for f1, f2 in semi_finals_pairs:
                if not f1 and not f2:
                    continue

                # Обработка BYE (если в одной из групп не хватило людей)
                if not f1 or not f2:
                    real_fighter = f1 or f2
                    fight, _ = Fight.objects.update_or_create(
                        tournament=bracket.tournament,
                        bracket=bracket,
                        round_number=playoff_round,
                        match_number=match_num,
                        defaults={
                            'age_weight_category': bracket.age_weight_category,
                            'fighter1': real_fighter,
                            'fighter2': None,
                            'status': 'completed',
                            'winner': real_fighter,
                            'win_method': 'walkover',
                            **fight_defaults
                        }
                    )
                    current_fights.append(fight)
                    match_num += 1
                    continue

                # Обычный бой
                fight, _ = Fight.objects.update_or_create(
                    tournament=bracket.tournament,
                    bracket=bracket,
                    round_number=playoff_round,
                    match_number=match_num,
                    defaults={
                        'age_weight_category': bracket.age_weight_category,
                        'fighter1': f1,
                        'fighter2': f2,
                        'status': 'scheduled',
                        **fight_defaults
                    }
                )
                current_fights.append(fight)
                match_num += 1

            # 6. Создаем финал
            if current_fights:
                next_round = playoff_round + 1
                final_fight, _ = Fight.objects.update_or_create(
                    tournament=bracket.tournament,
                    bracket=bracket,
                    round_number=next_round,
                    match_number=1,
                    defaults={
                        'age_weight_category': bracket.age_weight_category,
                        'status': 'scheduled',
                        'is_final': True,
                        **fight_defaults
                    }
                )

                # Связываем победителей полуфиналов с финалом
                for cf in current_fights:
                    cf.next_fight = final_fight
                    cf.save(update_fields=['next_fight'])

                # 7. Обновляем сетку, чтобы она знала о новых раундах
                bracket.total_rounds = next_round
                bracket.current_round = playoff_round
                bracket.save(update_fields=['total_rounds', 'current_round'])

                return True, "Перекрестный плей-офф создан (А1 vs Б2, Б1 vs А2)"

            return False, "Не удалось сформировать пары для плей-офф"

        except Exception as e:
            logger.error(f"Ошибка при создании плей-офф: {e}", exc_info=True)
            return False, f"Ошибка: {str(e)}"

    # ==================== СТАНДИНГИ ====================

    @staticmethod
    def _round_robin_standings(bracket, fights_queryset=None):
        # Если передали конкретные бои (например, только Группы А), берем их
        if fights_queryset is not None:
            fights = fights_queryset.filter(status='completed')
        else:
            fights = bracket.fights.filter(status='completed')

        stats = {}

        # Инициализация
        for f in fights:
            for fighter in (f.fighter1, f.fighter2):
                if fighter and fighter.id not in stats:
                    stats[fighter.id] = {
                        'fighter': fighter,
                        'wins': 0,
                        'draws': 0,
                        'losses': 0,
                        'points_for': 0,
                        'points_against': 0,
                        'head_to_head': {},  # {opponent_id: 'win'/'loss'/'draw'}
                    }

        # Заполнение статистики
        for f in fights:
            f1_id = f.fighter1_id
            f2_id = f.fighter2_id

            if f.winner:
                winner_id = f.winner_id
                loser_id = f2_id if winner_id == f1_id else f1_id
                if winner_id in stats:
                    stats[winner_id]['wins'] += 1
                if loser_id and loser_id in stats:
                    stats[loser_id]['losses'] += 1
                    stats[loser_id]['head_to_head'][winner_id] = 'loss'
                if winner_id in stats:
                    stats[winner_id]['head_to_head'][loser_id] = 'win'
            elif f.is_draw:
                if f1_id in stats:
                    stats[f1_id]['draws'] += 1
                    stats[f1_id]['head_to_head'][f2_id] = 'draw'
                if f2_id in stats:
                    stats[f2_id]['draws'] += 1
                    stats[f2_id]['head_to_head'][f1_id] = 'draw'

            if f1_id in stats:
                stats[f1_id]['points_for'] += f.score_fighter1
                stats[f1_id]['points_against'] += f.score_fighter2
            if f2_id in stats:
                stats[f2_id]['points_for'] += f.score_fighter2
                stats[f2_id]['points_against'] += f.score_fighter1

        def sort_key(item):
            fighter_id = item[0]
            data = item[1]
            wins = data['wins']
            draws = data['draws']
            diff = data['points_for'] - data['points_against']
            pts_for = data['points_for']
            # Первичная сортировка: победы, ничьи, разница очков, очки за
            return (wins, draws, diff, pts_for)

        # Сортируем
        sorted_items = sorted(stats.items(), key=sort_key, reverse=True)

        # Применяем tie-breaker: если у двух соседей равны ключи, смотрим личную встречу
        result = []
        i = 0
        while i < len(sorted_items):
            fid, data = sorted_items[i]
            # Ищем группу с одинаковым primary key
            group = [(fid, data)]
            j = i + 1
            while j < len(sorted_items):
                nfid, ndata = sorted_items[j]
                if sort_key((fid, data)) == sort_key((nfid, ndata)):
                    group.append((nfid, ndata))
                    j += 1
                else:
                    break

            # Если в группе > 1, сортируем по личной встрече
            if len(group) > 1:
                # Сортируем внутри группы: кто выиграл личную встречу — выше
                def h2h_sort(a, b):
                    aid, adata = a
                    bid, bdata = b
                    # Если a выиграл у b
                    if bdata['head_to_head'].get(aid) == 'loss':
                        return -1
                    if adata['head_to_head'].get(bid) == 'loss':
                        return 1
                    return 0

                # Простая сортировка пузырьком для маленьких групп
                for x in range(len(group)):
                    for y in range(x + 1, len(group)):
                        if h2h_sort(group[x], group[y]) > 0:
                            group[x], group[y] = group[y], group[x]

            for fid, data in group:
                result.append({
                    'place': None,  # Поставим после
                    'fighter': data['fighter'],
                    'method': f"Побед: {data['wins']}, Поражений: {data['losses']}, Очков: {data['points_for']}-{data['points_against']}"
                })
            i = j

        # Назначаем места
        for idx, item in enumerate(result, 1):
            item['place'] = idx if idx <= 3 else None

        return result

    @staticmethod
    def calculate_group_stats(group_fights):
        """Единая функция подсчета очков в группе (для таблицы и плей-офф)"""
        stats = {}

        # Инициализация
        for f in group_fights:
            for fighter in (f.fighter1, f.fighter2):
                if fighter and fighter.id not in stats:
                    stats[fighter.id] = {
                        'fighter': fighter, 'wins': 0, 'draws': 0, 'losses': 0,
                        'points': 0, 'score_diff': 0, 'place': None
                    }

        # Подсчет
        for f in group_fights.filter(status='completed'):
            if not f.fighter1 or not f.fighter2: continue
            s1 = stats.get(f.fighter1.id)
            s2 = stats.get(f.fighter2.id)
            if not s1 or not s2: continue

            s1['score_diff'] += (f.score_fighter1 - f.score_fighter2)
            s2['score_diff'] += (f.score_fighter2 - f.score_fighter1)

            if f.is_draw:
                s1['draws'] += 1;
                s1['points'] += 1
                s2['draws'] += 1;
                s2['points'] += 1
            elif f.winner_id == f.fighter1_id:
                s1['wins'] += 1;
                s1['points'] += 3
                s2['losses'] += 1
            elif f.winner_id == f.fighter2_id:
                s2['wins'] += 1;
                s2['points'] += 3
                s1['losses'] += 1

        # Жесткая спортивная сортировка:
        # 1. Очки (убывание)
        # 2. Разница набранных/пропущенных (убывание)
        # 3. Количество побед (убывание)
        # 4. ID (чтобы не было рандома, если всё абсолютно равно)
        sorted_stats = sorted(
            stats.values(),
            key=lambda x: (-x['points'], -x['score_diff'], -x['wins'], x['fighter'].id)
        )

        for idx, s in enumerate(sorted_stats):
            s['place'] = idx + 1

        return sorted_stats

    @staticmethod
    def _single_elimination_standings(bracket):
        fights = bracket.fights.all()
        max_round = fights.aggregate(models.Max('round_number'))['round_number__max']
        if not max_round:
            return []

        final = fights.filter(round_number=max_round).first()
        standings = []

        if final and final.status == 'completed' and final.winner:
            standings.append({
                'place': 1,
                'fighter': final.winner,
                'method': final.get_win_method_display() if final.win_method else 'Победа в финале'
            })
            if final.loser:
                standings.append({
                    'place': 2,
                    'fighter': final.loser,
                    'method': 'Финал'
                })

        third_fight = fights.filter(
            round_number=max_round, status='completed'
        ).exclude(id=final.id if final else None).first()

        if third_fight and third_fight.winner:
            standings.append({
                'place': 3,
                'fighter': third_fight.winner,
                'method': 'Матч за 3-е место'
            })
        else:
            semi = fights.filter(round_number=max_round - 1, status='completed') if max_round > 1 else []
            for sf in semi:
                if sf.loser and sf.loser not in [s['fighter'] for s in standings]:
                    standings.append({
                        'place': 3,
                        'fighter': sf.loser,
                        'method': 'Полуфиналист'
                    })

        return standings

    @staticmethod
    def _mixed_standings(bracket):
        playoff = bracket.fights.filter(round_number__gt=1)
        if not playoff.exists():
            # Если плей-офф ещё не создан, возвращаем standings группы
            return FightService._round_robin_standings(bracket)

        max_round = playoff.aggregate(models.Max('round_number'))['round_number__max']
        if not max_round:
            return []

        final = playoff.filter(round_number=max_round).first()
        standings = []

        if final and final.status == 'completed' and final.winner:
            standings.append({
                'place': 1,
                'fighter': final.winner,
                'method': final.get_win_method_display() if final.win_method else 'Победа в финале'
            })
            if final.loser:
                standings.append({
                    'place': 2,
                    'fighter': final.loser,
                    'method': 'Финал'
                })

        third_fight = playoff.filter(
            round_number=max_round, status='completed'
        ).exclude(id=final.id if final else None).first()

        if third_fight and third_fight.winner:
            standings.append({
                'place': 3,
                'fighter': third_fight.winner,
                'method': 'Матч за 3-е место'
            })
        else:
            semi = playoff.filter(round_number=max_round - 1, status='completed') if max_round > 2 else []
            for sf in semi:
                if sf.loser and sf.loser not in [s['fighter'] for s in standings]:
                    standings.append({
                        'place': 3,
                        'fighter': sf.loser,
                        'method': 'Полуфиналист'
                    })

        return standings