from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Доступ к элементу словаря по ключу: {{ mydict|get_item:key }}"""
    if dictionary is None:
        return None
    try:
        return dictionary.get(key)
    except (AttributeError, TypeError):
        return None


@register.filter
def get_participants(fights):
    """Из списка боёв возвращает уникальных участников (fighter1 + fighter2)"""
    participants = []
    seen_ids = set()
    for fight in fights:
        for fighter in (fight.fighter1, fight.fighter2):
            if fighter and fighter.id not in seen_ids:
                seen_ids.add(fighter.id)
                participants.append(fighter)
    return participants


@register.filter
def count_wins(fights, fighter):
    """Считает победы бойца в списке боёв"""
    count = 0
    for fight in fights:
        if fight.status == 'completed' and fight.winner == fighter:
            count += 1
    return count


@register.filter
def get_fight_between(fights, pair):
    """Возвращает бой между двумя бойцами. pair = [fighter1, fighter2]"""
    f1, f2 = pair
    for fight in fights:
        if (fight.fighter1 == f1 and fight.fighter2 == f2) or \
           (fight.fighter1 == f2 and fight.fighter2 == f1):
            return fight
    return None
