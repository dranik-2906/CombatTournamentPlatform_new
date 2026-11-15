from datetime import date
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

MIN_BIRTH_YEAR = 1900
MIN_AGE = 4
MAX_WEIGHT_KG = 300


def validate_birth_date(value):
    today = date.today()
    min_date = date(MIN_BIRTH_YEAR, 1, 1)
    if value > today:
        raise ValidationError(_('Дата рождения не может быть в будущем'))
    if value < min_date:
        raise ValidationError(_('Дата рождения не может быть раньше %(year)s г.'), params={'year': MIN_BIRTH_YEAR})

    age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
    if age < MIN_AGE:
        raise ValidationError(_('Участнику должно быть не менее %(min)s лет'), params={'min': MIN_AGE})


def validate_weight(value):
    if value is None:
        raise ValidationError(_('Вес обязателен'))
    if value <= 0:
        raise ValidationError(_('Вес должен быть больше нуля'))
    if value > MAX_WEIGHT_KG:
        raise ValidationError(_('Вес %(value)s кг выглядит ошибочным'), params={'value': value})