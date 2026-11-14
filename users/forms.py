from django import forms
from django.contrib.auth.models import User
from .models import Federation
from tournaments.models.tournament import SPORT_TYPES # Импортируем виды спорта из турниров

class FederationCreateForm(forms.ModelForm):
    admin_username = forms.CharField(max_length=150, label="Логин администратора", widget=forms.TextInput(attrs={'class': 'form-control'}))
    admin_email = forms.EmailField(label="Email администратора", widget=forms.EmailInput(attrs={'class': 'form-control'}))
    admin_password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}), label="Пароль")

    # НОВОЕ ПОЛЕ: выбор видов спорта (чекбоксы)
    sports = forms.MultipleChoiceField(
        choices=SPORT_TYPES,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        label="Разрешенные виды спорта",
        required=True
    )

    class Meta:
        model = Federation
        fields = ['name', 'description', 'valid_until']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'valid_until': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def clean_admin_username(self):
        username = self.cleaned_data.get('admin_username')
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Пользователь с таким логином уже существует!")
        return username

    def save(self, commit=True):
        federation = super().save(commit=False)
        # Сохраняем выбранные виды спорта в виде строки через запятую
        federation.sports = ",".join(self.cleaned_data['sports'])
        if commit:
            federation.save()
        return federation