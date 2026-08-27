from django.test import TestCase
from django.contrib.auth.models import User
from .models import Tournament, Fighter, Judge, AgeWeightCategory, Bracket, Fight, TournamentRegistration
from .services import CategoryService, BracketService, FightService


class CategoryServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testfighter', password='testpass')
        self.tournament = Tournament.objects.create(
            name='Test Tournament', start_date='2024-01-01', end_date='2024-01-02', location='Moscow'
        )
        self.category = AgeWeightCategory.objects.create(
            tournament=self.tournament, name='U16 -60kg', gender='M',
            min_birth_year=2008, max_birth_year=2010,
            min_weight=55, max_weight=60
        )
        self.fighter = Fighter.objects.create(
            user=self.user, first_name='Ivan', last_name='Ivanov',
            date_of_birth='2009-05-15', gender='M', weight=58, club='Dynamo', coach='Petrov'
        )
        self.reg = TournamentRegistration.objects.create(
            tournament=self.tournament, fighter=self.fighter
        )

    def test_find_category(self):
        cat = CategoryService.find_category(self.tournament, 'M', 2009, 58.0)
        self.assertEqual(cat, self.category)

    def test_auto_assign(self):
        result = CategoryService.auto_assign_categories(self.tournament)
        self.assertEqual(result['success'], 1)
        self.reg.refresh_from_db()
        self.assertEqual(self.reg.age_weight_category, self.category)


class BracketServiceTests(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(
            name='Test', start_date='2024-01-01', end_date='2024-01-02', location='Moscow'
        )
        self.category = AgeWeightCategory.objects.create(
            tournament=self.tournament, name='Open', gender='M',
            min_birth_year=1990, max_birth_year=2010, min_weight=50, max_weight=100
        )
        self.bracket = Bracket.objects.create(
            tournament=self.tournament, age_weight_category=self.category,
            bracket_type='single_elimination'
        )
        # Create 4 fighters
        self.participants = []
        for i in range(4):
            user = User.objects.create_user(username=f'fighter{i}', password='testpass')
            fighter = Fighter.objects.create(
                user=user, first_name=f'Fighter', last_name=f'{i}',
                date_of_birth='2000-01-01', gender='M', weight=70, club='Test', coach='Coach'
            )
            reg = TournamentRegistration.objects.create(
                tournament=self.tournament, fighter=fighter, age_weight_category=self.category, is_approved=True
            )
            self.participants.append(reg)

    def test_generate_single_elimination(self):
        success, msg = BracketService.generate_single_elimination(self.bracket, self.participants)
        self.assertTrue(success)
        self.assertEqual(Fight.objects.filter(bracket=self.bracket).count(), 4)  # 2 real + 2 byes for 4 participants

    def test_advance_winners(self):
        BracketService.generate_single_elimination(self.bracket, self.participants)
        # Complete round 1 fights
        for fight in Fight.objects.filter(bracket=self.bracket, round_number=1):
            if fight.fighter2:
                fight.winner = fight.fighter1
                fight.status = 'completed'
                fight.save()
        success, msg = BracketService.advance_winners(self.bracket)
        self.assertTrue(success)
