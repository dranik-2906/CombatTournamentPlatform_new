from django import forms
from django.contrib.auth.models import User
import uuid
from users.models import Profile
from .models import (
    Tournament, AgeWeightCategory, WeightCategory, AgeGroup,
    Fighter, Judge, Bracket, Fight, TimerSettings, TournamentRegistration,
    TournamentCheckpoint
)


class TournamentForm(forms.ModelForm):
    class Meta:
        model = Tournament
        fields = ['name', 'sport_type', 'start_date', 'end_date', 'location', 'description', 'bracket_type']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Название турнира'}),
            'sport_type': forms.TextInput(attrs={'class': 'form-control'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Место проведения'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'bracket_type': forms.Select(attrs={'class': 'form-select'}),
        }


class AgeWeightCategoryForm(forms.ModelForm):
    class Meta:
        model = AgeWeightCategory
        fields = ['name', 'gender', 'min_birth_year', 'max_birth_year', 'min_weight', 'max_weight', 'bracket_system']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'min_birth_year': forms.NumberInput(attrs={'class': 'form-control'}),
            'max_birth_year': forms.NumberInput(attrs={'class': 'form-control'}),
            'min_weight': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'max_weight': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'bracket_system': forms.Select(attrs={'class': 'form-select'}),
        }

    def clean(self):
        cleaned = super().clean()
        min_weight = cleaned.get('min_weight')
        max_weight = cleaned.get('max_weight')
        min_year = cleaned.get('min_birth_year')
        max_year = cleaned.get('max_birth_year')

        if min_weight and max_weight and min_weight >= max_weight:
            self.add_error('max_weight', 'Максимальный вес должен быть больше минимального')
        if min_year and max_year and min_year > max_year:
            self.add_error('max_birth_year', 'Максимальный год должен быть больше минимального')
        return cleaned


class WeightCategoryForm(forms.ModelForm):
    class Meta:
        model = WeightCategory
        fields = ['name', 'min_weight', 'max_weight', 'gender']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'min_weight': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'max_weight': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'gender': forms.Select(attrs={'class': 'form-select'}),
        }


class FighterForm(forms.ModelForm):
    class Meta:
        model = Fighter
        fields = ['first_name', 'last_name', 'date_of_birth', 'gender', 'weight', 'club', 'coach', 'photo']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'date_of_birth': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'weight': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'club': forms.TextInput(attrs={'class': 'form-control'}),
            'coach': forms.TextInput(attrs={'class': 'form-control'}),
            'photo': forms.FileInput(attrs={'class': 'form-control'}),
        }

    def save(self, commit=True):
        fighter = super().save(commit=False)

        # Проверяем, не существует ли уже такой боец
        existing = Fighter.objects.filter(
            first_name__iexact=fighter.first_name,
            last_name__iexact=fighter.last_name,
            date_of_birth=fighter.date_of_birth,
            club__iexact=fighter.club
        ).first()

        if existing:
            # Обновляем вес и тренера, если изменились
            existing.weight = fighter.weight
            existing.coach = fighter.coach
            if fighter.photo:
                existing.photo = fighter.photo
            existing.save()
            return existing

        # Пароль: fighter + ДДММГГ (например, fighter290605)
        password = f"fighter{fighter.date_of_birth.strftime('%d%m%y')}"

        # Временный уникальный username, чтобы пройти UNIQUE constraint
        temp_username = f"temp_{uuid.uuid4().hex[:12]}"

        user = User.objects.create_user(
            username=temp_username,
            email='',
            first_name=fighter.first_name,
            last_name=fighter.last_name,
            password=password
        )

        fighter.user = user
        if commit:
            fighter.save()
            # Теперь fighter имеет ID — обновляем username на fighter{id}
            user.username = f"fighter{fighter.id}"
            user.save(update_fields=['username'])

        return fighter


class JudgeForm(forms.ModelForm):
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={'class': 'form-control'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}), required=False)

    class Meta:
        model = Judge
        fields = ['first_name', 'last_name', 'category', 'judge_type', 'license_number', 'experience_years']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'judge_type': forms.Select(attrs={'class': 'form-select'}),
            'license_number': forms.TextInput(attrs={'class': 'form-control'}),
            'experience_years': forms.NumberInput(attrs={'class': 'form-control'}),
        }

    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip()
        if not username:
            raise forms.ValidationError('Имя пользователя обязательно')
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError(f'Пользователь с логином «{username}» уже существует.')
        return username

    def save(self, commit=True):
        judge = super().save(commit=False)
        username = self.cleaned_data.get('username', '').strip()

        try:
            user = User.objects.get(username__iexact=username)
        except User.DoesNotExist:
            user_data = {
                'username': username,
                'email': self.cleaned_data.get('email', ''),
                'first_name': judge.first_name,
                'last_name': judge.last_name,
            }
            password = self.cleaned_data.get('password')
            if password:
                user = User.objects.create_user(**user_data, password=password)
            else:
                user = User.objects.create_user(**user_data)

        # Устанавливаем роль судьи в профиле
        profile, _ = Profile.objects.get_or_create(user=user)
        profile.role = 'judge'
        profile.save()

        judge.user = user
        if commit:
            judge.save()
        return judge


# ---------- Форма для результата боя ----------
class FightResultForm(forms.ModelForm):
    class Meta:
        model = Fight
        fields = ['winner', 'win_method', 'judge_notes', 'score_fighter1', 'score_fighter2', 'is_draw']
        widgets = {
            'winner': forms.Select(attrs={'class': 'form-select'}),
            'win_method': forms.Select(attrs={'class': 'form-select'}),
            'judge_notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'score_fighter1': forms.NumberInput(attrs={'class': 'form-control'}),
            'score_fighter2': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_draw': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, fight=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Ограничиваем победителя только двумя участниками боя (исключаем None)
        if fight:
            fighter_ids = [fid for fid in (fight.fighter1_id, fight.fighter2_id) if fid]
            self.fields['winner'].queryset = Fighter.objects.filter(id__in=fighter_ids)
        elif self.instance and self.instance.pk:
            fighter_ids = [fid for fid in (self.instance.fighter1_id, self.instance.fighter2_id) if fid]
            self.fields['winner'].queryset = Fighter.objects.filter(id__in=fighter_ids)
        else:
            self.fields['winner'].queryset = Fighter.objects.none()


class TimerSettingsForm(forms.ModelForm):
    class Meta:
        model = TimerSettings
        fields = ['round_duration', 'break_duration', 'number_of_rounds', 'warning_sound', 'final_warning']
        widgets = {
            'round_duration': forms.Select(attrs={'class': 'form-select'}),
            'break_duration': forms.Select(attrs={'class': 'form-select'}),
            'number_of_rounds': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 10}),
            'warning_sound': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'final_warning': forms.NumberInput(attrs={'class': 'form-control'}),
        }


class AssignJudgeForm(forms.Form):
    judge = forms.ModelChoiceField(
        queryset=Judge.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Судья',
        empty_label='-- Выберите судью --'
    )
    assign_to_category = forms.BooleanField(
        required=False, initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label='Назначить на все бои категории'
    )


class ExcelUploadForm(forms.Form):
    excel_file = forms.FileField(
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.xlsx,.xls'}),
        label='Файл Excel'
    )


class TournamentCheckpointForm(forms.ModelForm):
    class Meta:
        model = TournamentCheckpoint
        fields = ['name', 'code', 'order', 'is_required']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Например, Медосмотр'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '1 буква, например М'}),
            'order': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'is_required': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': 'Название чекпоинта',
            'code': 'Код (буква)',
            'order': 'Порядок отображения',
            'is_required': 'Обязательный для допуска',
        }