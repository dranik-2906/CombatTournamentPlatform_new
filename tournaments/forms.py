from django import forms
from django.contrib.auth.models import User
from django.core.validators import FileExtensionValidator
from django.utils import timezone  # ← добавлено для проверки дат
from .models import Tournament, AgeWeightCategory, TournamentRegistration, Judge, TimerSettings, Fight, RoundScore, \
    Fighter, TournamentCheckpoint
from .models.tournament import SPORT_TYPES
from .validators import validate_birth_date, validate_weight


class TournamentForm(forms.ModelForm):
    class Meta:
        model = Tournament
        fields = ['name', 'sport_type', 'start_date', 'end_date', 'location', 'description', 'bracket_type']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'sport_type': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'bracket_type': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        # ВАЖНО: сохраняем user в self, чтобы иметь к нему доступ в clean()
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if self.user and not self.user.is_superuser and hasattr(self.user, 'profile') and self.user.profile.federation:
            federation = self.user.profile.federation
            if federation.sports:
                allowed_sports = [s.strip() for s in federation.sports.split(',') if s.strip()]
                self.fields['sport_type'].choices = [
                    (value, label) for value, label in self.fields['sport_type'].choices
                    if value in allowed_sports
                ]

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        today = timezone.now().date()

        # 1. Дата окончания не может быть раньше даты начала
        if start_date and end_date and start_date > end_date:
            self.add_error('end_date', 'Дата окончания не может быть раньше даты начала')

        # 2. Нельзя создавать турниры, которые уже закончились
        # (суперпользователь — исключение, чтобы можно было вносить исторические турниры)
        if end_date and end_date < today and not (self.user and self.user.is_superuser):
            self.add_error(
                'end_date',
                'Дата окончания не может быть в прошлом. '
                'Вы пытаетесь создать уже завершённый турнир.'
            )

        return cleaned_data


class AgeWeightCategoryForm(forms.ModelForm):
    class Meta:
        model = AgeWeightCategory
        fields = ['name', 'gender', 'min_birth_year', 'max_birth_year', 'min_weight', 'max_weight', 'bracket_system',
                  'side_judges_count']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'min_birth_year': forms.NumberInput(attrs={'class': 'form-control'}),
            'max_birth_year': forms.NumberInput(attrs={'class': 'form-control'}),
            'min_weight': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'max_weight': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'bracket_system': forms.Select(attrs={'class': 'form-select'}),
            'side_judges_count': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 10}),
        }

    def clean(self):
        cleaned = super().clean()
        min_weight = cleaned.get('min_weight')
        max_weight = cleaned.get('max_weight')
        min_year = cleaned.get('min_birth_year')
        max_year = cleaned.get('max_birth_year')
        side_judges = cleaned.get('side_judges_count', 0)

        if min_weight and max_weight and min_weight >= max_weight:
            self.add_error('max_weight', 'Максимальный вес должен быть больше минимального')
        if min_year and max_year and min_year > max_year:
            self.add_error('max_birth_year', 'Максимальный год должен быть больше минимального')
        if side_judges and side_judges < 0:
            self.add_error('side_judges_count', 'Не может быть отрицательным')
        return cleaned


class TournamentRegistrationForm(forms.ModelForm):
    class Meta:
        model = TournamentRegistration
        fields = ['age_weight_category']
        widgets = {
            'age_weight_category': forms.Select(attrs={'class': 'form-select'}),
        }


class AssignJudgeForm(forms.Form):
    judge = forms.ModelChoiceField(
        queryset=Judge.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Выберите судью'
    )
    assign_to_category = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label='Назначить на все бои категории'
    )


class FightResultForm(forms.ModelForm):
    class Meta:
        model = Fight
        fields = ['winner', 'win_method', 'judge_notes', 'is_draw', 'score_fighter1', 'score_fighter2']
        widgets = {
            'winner': forms.Select(attrs={'class': 'form-select'}),
            'win_method': forms.Select(attrs={'class': 'form-select'}),
            'judge_notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_draw': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'score_fighter1': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'score_fighter2': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
        }

    def __init__(self, *args, fight=None, **kwargs):
        super().__init__(*args, **kwargs)
        if fight and fight.fighter1 and fight.fighter2:
            self.fields['winner'].choices = [
                ('', '---------'),
                (fight.fighter1.id, f"{fight.fighter1.full_name} (Боец 1)"),
                (fight.fighter2.id, f"{fight.fighter2.full_name} (Боец 2)"),
            ]

        # ИСПРАВЛЕНИЕ: Не делаем поля обязательными на уровне HTML,
        # проверка происходит в clean() с учетом галочки "Ничья"
        self.fields['winner'].required = False
        self.fields['win_method'].required = False

    def clean(self):
        cleaned_data = super().clean()
        is_draw = cleaned_data.get('is_draw')
        winner = cleaned_data.get('winner')
        win_method = cleaned_data.get('win_method')

        if is_draw:
            # ИСПРАВЛЕНИЕ: При ничьей обнуляем победителя
            cleaned_data['winner'] = None
        else:
            # Если не ничья - победитель и метод строго обязательны
            if not winner:
                self.add_error('winner', 'Вы должны выбрать победителя!')
            if not win_method:
                self.add_error('win_method', 'Вы должны выбрать метод победы!')

        return cleaned_data


class JudgeForm(forms.ModelForm):
    class Meta:
        model = Judge
        fields = ['first_name', 'last_name', 'date_of_birth', 'category', 'judge_type', 'license_number',
                  'experience_years', 'is_active']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'date_of_birth': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'judge_type': forms.Select(attrs={'class': 'form-select'}),
            'license_number': forms.TextInput(attrs={'class': 'form-control'}),
            'experience_years': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'date_of_birth': 'Дата рождения (для пароля)',
            'judge_type': 'Тип судьи',
        }

    def clean_date_of_birth(self):
        dob = self.cleaned_data.get('date_of_birth')
        if dob:
            validate_birth_date(dob)
        return dob


class TimerSettingsForm(forms.ModelForm):
    class Meta:
        model = TimerSettings
        fields = ['round_duration', 'break_duration', 'number_of_rounds']
        widgets = {
            'round_duration': forms.NumberInput(attrs={'class': 'form-control'}),
            'break_duration': forms.NumberInput(attrs={'class': 'form-control'}),
            'number_of_rounds': forms.NumberInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'round_duration': 'Длительность раунда (секунды)',
            'break_duration': 'Длительность перерыва (секунды)',
            'number_of_rounds': 'Количество раундов',
        }


class RoundScoreForm(forms.ModelForm):
    class Meta:
        model = RoundScore
        fields = ['round_number', 'score_fighter1', 'score_fighter2']
        widgets = {
            'round_number': forms.NumberInput(attrs={'class': 'form-control', 'readonly': True}),
            'score_fighter1': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'score_fighter2': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
        }


# ==================== ФОРМЫ ДЛЯ PARTICIPANTS ====================

class FighterForm(forms.ModelForm):
    class Meta:
        model = Fighter
        fields = ['first_name', 'last_name', 'date_of_birth', 'gender', 'weight', 'club', 'coach', 'photo']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'date_of_birth': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'weight': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'club': forms.TextInput(attrs={'class': 'form-control'}),
            'coach': forms.TextInput(attrs={'class': 'form-control'}),
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

    def clean_date_of_birth(self):
        dob = self.cleaned_data.get('date_of_birth')
        if dob:
            validate_birth_date(dob)
        return dob

    def clean_weight(self):
        weight = self.cleaned_data.get('weight')
        # ИСПРАВЛЕНИЕ: Проверяем на None, чтобы 0 не проскочил как "пустое" значение
        if weight is not None:
            validate_weight(weight)
        return weight


class ExcelUploadForm(forms.Form):
    excel_file = forms.FileField(
        label='Excel-файл',
        # ИСПРАВЛЕНИЕ: Валидация расширения на сервере, а не только в браузере
        validators=[FileExtensionValidator(allowed_extensions=['xlsx'])],
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.xlsx'})
    )


class TournamentCheckpointForm(forms.ModelForm):
    class Meta:
        model = TournamentCheckpoint
        fields = ['name', 'code', 'order', 'is_required']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'order': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_required': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }