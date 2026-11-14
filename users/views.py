from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.views.decorators.http import require_http_methods
from django.db import transaction
from .models import Profile, Federation

# Импортируем нашу новую форму для создания федерации вместе с админом
from .forms import FederationCreateForm


# Доступ только для системного админа (суперпользователя)
@user_passes_test(lambda u: u.is_superuser)
def federation_list(request):
    """Список всех федераций"""
    federations = Federation.objects.all().order_by('-created_at')
    return render(request, 'users/federation_list.html', {'federations': federations})


@user_passes_test(lambda u: u.is_superuser)
def create_federation(request):
    """Создание федерации и её администратора в один клик"""
    if request.method == 'POST':
        form = FederationCreateForm(request.POST)
        if form.is_valid():
            try:
                # Используем транзакцию, чтобы если что-то упадет, база не засорилась
                with transaction.atomic():
                    # 1. Сохраняем Федерацию
                    federation = form.save(commit=False)
                    federation.is_active = True
                    federation.save()

                    # 2. Создаем Пользователя для админа федерации
                    username = form.cleaned_data['admin_username']
                    email = form.cleaned_data['admin_email']
                    password = form.cleaned_data['admin_password']

                    user = User.objects.create_user(username=username, email=email, password=password)

                    # 3. Назначаем роль и привязываем к федерации
                    # Профиль создается автоматически через сигнал в models.py
                    profile = user.profile
                    profile.role = 'tournament_admin'
                    profile.federation = federation
                    profile.save()

                messages.success(request,
                                 f'Федерация "{federation.name}" и аккаунт администратора "{username}" успешно созданы!')
                return redirect('users:federation_list')
            except Exception as e:
                messages.error(request, f'Ошибка при создании: {e}')
    else:
        form = FederationCreateForm()

    return render(request, 'users/federation_form.html', {'form': form})


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