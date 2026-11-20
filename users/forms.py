from django import forms
from django.contrib.auth.models import User
from .models import Federation, Profile
from tournaments.models.tournament import SPORT_TYPES
from geo.models import Country, City

# ==================== ФОРМА ДЛЯ ЛИЧНОГО КАБИНЕТА ====================

class UserUpdateForm(forms.ModelForm):
    """Форма для изменения базовых данных пользователя (логин, email, ФИО)"""
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'username': 'Логин',
            'first_name': 'Имя',
            'last_name': 'Фамилия',
            'email': 'Email',
        }

class ProfileForm(forms.ModelForm):
    """Форма для изменения данных профиля (клуб, страна, город, аватар)"""
    class Meta:
        model = Profile
        fields = ['club', 'country', 'city', 'photo'] # <-- Добавлено photo
        widgets = {
            'club': forms.TextInput(attrs={'class': 'form-control'}),
            'country': forms.Select(attrs={'class': 'form-select'}),
            'city': forms.Select(attrs={'class': 'form-select'}),
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

# ==================== ФОРМА ДЛЯ СОЗДАНИЯ ФЕДЕРАЦИИ ====================

class FederationCreateForm(forms.ModelForm):
    admin_username = forms.CharField(max_length=150, label="Логин администратора", widget=forms.TextInput(attrs={'class': 'form-control'}))
    admin_email = forms.EmailField(label="Email администратора", widget=forms.EmailInput(attrs={'class': 'form-control'}))
    admin_password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}), label="Пароль")

    sports = forms.MultipleChoiceField(
        choices=SPORT_TYPES,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        label="Разрешенные виды спорта",
        required=True
    )

    class Meta:
        model = Federation
        fields = ['name', 'description', 'valid_until', 'country', 'city']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'valid_until': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'country': forms.Select(attrs={'class': 'form-select'}),
            'city': forms.Select(attrs={'class': 'form-select'}),
        }

    def clean_admin_username(self):
        username = self.cleaned_data.get('admin_username')
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Пользователь с таким логином уже существует!")
        return username

    def save(self, commit=True):
        federation = super().save(commit=False)
        federation.sports = ",".join(self.cleaned_data['sports'])
        if commit:
            federation.save()
        return federation