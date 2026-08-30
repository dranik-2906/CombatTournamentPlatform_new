import logging
import math
from django.db import models
from django.utils import timezone
from ..models import Fight, RoundScore

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
        """Определение призёров (1-2-3 место) для любого типа сетки"""
        if not bracket.fights.filter(status='completed').exists():
            return []

        if bracket.bracket_type == 'round_robin':
            return FightService._round_robin_standings(bracket)
        elif bracket.bracket_type == 'single_elimination':
            return FightService._single_elimination_standings(bracket)
        elif bracket.bracket_type == 'mixed':
            return FightService._mixed_standings(bracket)
        return []

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
            fight.bracket.winner = winner.full_name if winner else None
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
    def create_playoff_from_round_robin(bracket, advancing_count=None):
        """Создать плей-офф из round-robin standings"""
        from ..models import Fight

        standings = FightService.get_standings(bracket)
        # Берём только тех, у кого определено место (place не None)
        advancing = [s['fighter'] for s in standings if s['place'] and s['place'] <= (advancing_count or 4)]

        if not advancing_count:
            fighter_ids = set()
            for f in bracket.fights.all():
                if f.fighter1_id:
                    fighter_ids.add(f.fighter1_id)
                if f.fighter2_id:
                    fighter_ids.add(f.fighter2_id)
            advancing_count = 8 if len(fighter_ids) >= 16 else 4
            advancing = [s['fighter'] for s in standings if s['place'] and s['place'] <= advancing_count]

        if len(advancing) < 2:
            return False, "Недостаточно участников для плей-офф"

        num = len(advancing)
        rounds_needed = math.ceil(math.log2(num))
        total_slots = 2 ** rounds_needed

        while len(advancing) < total_slots:
            advancing.append(None)

        max_round = bracket.fights.aggregate(models.Max('round_number'))['round_number__max'] or 1
        playoff_round = max_round + 1

        current_fights = []
        match_num = 1
        for i in range(0, len(advancing), 2):
            f1 = advancing[i]
            f2 = advancing[i + 1]

            if not f1 and not f2:
                continue

            if not f1 or not f2:
                real_fighter = f1 or f2
                fight = Fight.objects.create(
                    tournament=bracket.tournament,
                    bracket=bracket,
                    age_weight_category=bracket.age_weight_category,
                    round_number=playoff_round,
                    match_number=match_num,
                    fighter1=real_fighter,
                    fighter2=None,
                    status='completed',
                    winner=real_fighter,
                    win_method='walkover',
                )
                current_fights.append(fight)
                match_num += 1
                continue

            fight = Fight.objects.create(
                tournament=bracket.tournament,
                bracket=bracket,
                age_weight_category=bracket.age_weight_category,
                round_number=playoff_round,
                match_number=match_num,
                fighter1=f1,
                fighter2=f2,
                status='scheduled',
            )
            current_fights.append(fight)
            match_num += 1

        while len(current_fights) > 1:
            next_fights = []
            next_round = playoff_round + 1
            match_num = 1
            for i in range(0, len(current_fights), 2):
                next_fight = Fight.objects.create(
                    tournament=bracket.tournament,
                    bracket=bracket,
                    age_weight_category=bracket.age_weight_category,
                    round_number=next_round,
                    match_number=match_num,
                    status='scheduled',
                )
                current_fights[i].next_fight = next_fight
                current_fights[i].save(update_fields=['next_fight'])
                if i + 1 < len(current_fights):
                    current_fights[i + 1].next_fight = next_fight
                    current_fights[i + 1].save(update_fields=['next_fight'])
                next_fights.append(next_fight)
                match_num += 1
            current_fights = next_fights
            playoff_round = next_round

        if current_fights:
            current_fights[0].is_final = True
            current_fights[0].save(update_fields=['is_final'])

        return True, f"Плей-офф создан: {num} участников, {math.ceil(math.log2(num))} раунд(ов)"

    # ==================== СТАНДИНГИ ====================

    @staticmethod
    def _round_robin_standings(bracket):
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