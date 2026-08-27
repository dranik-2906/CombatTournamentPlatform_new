from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.views.decorators.http import require_http_methods
from .models import Profile


def login_view(request):
    """Вход в систему"""
    if request.user.is_authenticated:
        return redirect('core:dashboard')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            next_url = request.GET.get('next', 'core:dashboard')
            return redirect(next_url)
        else:
            messages.error(request, 'Неверное имя пользователя или пароль')
    else:
        form = AuthenticationForm()

    return render(request, 'users/login.html', {'form': form})


@require_http_methods(["GET", "POST"])
def logout_view(request):
    """Выход из системы"""
    logout(request)
    messages.success(request, 'Вы вышли из системы')
    return redirect('home')


def register(request):
    """Регистрация нового участника"""
    if request.user.is_authenticated:
        return redirect('core:dashboard')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')
        email = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()

        errors = []
        if not username:
            errors.append('Введите имя пользователя')
        if User.objects.filter(username=username).exists():
            errors.append('Пользователь с таким именем уже существует')
        if len(password1) < 6:
            errors.append('Пароль должен содержать минимум 6 символов')
        if password1 != password2:
            errors.append('Пароли не совпадают')

        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, 'users/register.html', {
                'username': username,
                'email': email,
                'first_name': first_name,
                'last_name': last_name,
            })

        try:
            user = User.objects.create_user(
                username=username, email=email, password=password1,
                first_name=first_name, last_name=last_name
            )
            Profile.objects.get_or_create(user=user, defaults={'role': 'fighter'})
            login(request, user)
            messages.success(request, f'Добро пожаловать, {username}!')
            return redirect('core:dashboard')
        except Exception as e:
            messages.error(request, f'Ошибка регистрации: {e}')

    return render(request, 'users/register.html')
