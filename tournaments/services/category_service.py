import logging
from ..models import AgeWeightCategory, TournamentRegistration

logger = logging.getLogger('tournaments')


class CategoryService:
    """Сервис для работы с категориями и распределением участников"""

    @staticmethod
    def auto_assign_categories(tournament):
        """Автоматическое распределение участников по категориям"""
        categories = AgeWeightCategory.objects.filter(tournament=tournament)
        if not categories.exists():
            return {'success': 0, 'skipped': 0, 'failed': 0, 'errors': ['Нет категорий']}

        registrations = TournamentRegistration.objects.filter(
            tournament=tournament, is_approved=True
        ).select_related('fighter')

        stats = {'success': 0, 'skipped': 0, 'failed': 0, 'errors': []}

        for reg in registrations:
            fighter = reg.fighter

            if reg.age_weight_category:
                stats['skipped'] += 1
                continue

            if not fighter.date_of_birth or not fighter.weight:
                stats['failed'] += 1
                stats['errors'].append(f"{fighter}: нет данных о возрасте или весе")
                continue

            birth_year = fighter.date_of_birth.year
            weight = float(fighter.weight)

            category = CategoryService.find_category(
                tournament, fighter.gender, birth_year, weight
            )

            if category:
                reg.age_weight_category = category
                reg.save(update_fields=['age_weight_category'])
                stats['success'] += 1
                logger.debug(f"{fighter} -> {category.name}")
            else:
                stats['failed'] += 1
                stats['errors'].append(f"{fighter}: нет подходящей категории")

        logger.info(f"Распределение по категориям: {stats['success']} успешно, "
                    f"{stats['skipped']} пропущено, {stats['failed']} не удалось")
        return stats

    @staticmethod
    def find_category(tournament, gender, birth_year, weight):
        """Найти подходящую категорию для бойца"""
        categories = AgeWeightCategory.objects.filter(
            tournament=tournament,
            gender=gender,
            min_birth_year__lte=birth_year,
            max_birth_year__gte=birth_year,
        )
        for cat in categories:
            if cat.min_weight <= weight <= cat.max_weight:
                return cat
        return None

    @staticmethod
    def validate_assignment(registration, category):
        """Проверить соответствие бойца категории"""
        fighter = registration.fighter
        warnings = []
        is_valid = True

        if fighter.date_of_birth:
            by = fighter.date_of_birth.year
            if not (category.min_birth_year <= by <= category.max_birth_year):
                warnings.append(f"год рождения {by} вне диапазона")
                is_valid = False

        if fighter.weight:
            if not (category.min_weight <= float(fighter.weight) <= category.max_weight):
                warnings.append(f"вес {fighter.weight}кг вне диапазона")
                is_valid = False

        if fighter.gender != category.gender:
            warnings.append(f"пол не соответствует")
            is_valid = False

        return is_valid, warnings
