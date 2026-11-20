from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.models import User
from django.views.decorators.http import require_http_methods
from django.db import transaction
from .models import Profile, Federation

from .forms import FederationCreateForm, UserUpdateForm, ProfileForm
from tournaments.forms import FighterForm, JudgeForm


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
                with transaction.atomic():
                    federation = form.save(commit=False)
                    federation.is_active = True
                    federation.save()

                    username = form.cleaned_data['admin_username']
                    email = form.cleaned_data['admin_email']
                    password = form.cleaned_data['admin_password']

                    user = User.objects.create_user(username=username, email=email, password=password)

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


# ==================== ЛИЧНЫЙ КАБИНЕТ ====================

@login_required
def profile_view(request):
    """Личный кабинет пользователя"""
    user = request.user
    user_form = UserUpdateForm(instance=user)
    profile_form = ProfileForm(instance=user.profile)
    password_form = PasswordChangeForm(user)

    fighter_form = FighterForm(instance=user.fighter) if hasattr(user, 'fighter') else None
    judge_form = JudgeForm(instance=user.judge) if hasattr(user, 'judge') else None

    if request.method == 'POST':
        # ОБНОВЛЕНИЕ ДАННЫХ
        if 'update_profile' in request.POST:
            user_form = UserUpdateForm(request.POST, instance=user)

            # ВАЖНО: Добавлен request.FILES для загрузки аватарки!
            profile_form = ProfileForm(request.POST, request.FILES, instance=user.profile)

            if fighter_form:
                fighter_form = FighterForm(request.POST, request.FILES, instance=user.fighter)
            if judge_form:
                judge_form = JudgeForm(request.POST, instance=user.judge)

            if user_form.is_valid() and profile_form.is_valid() and \
                    (not fighter_form or fighter_form.is_valid()) and \
                    (not judge_form or judge_form.is_valid()):

                user_form.save()
                profile_form.save()
                if fighter_form: fighter_form.save()
                if judge_form: judge_form.save()

                messages.success(request, 'Профиль успешно обновлён!')
                return redirect('users:profile')

        # СМЕНА ПАРОЛЯ
        elif 'change_password' in request.POST:
            password_form = PasswordChangeForm(user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, 'Пароль успешно изменён!')
                return redirect('users:profile')

    context = {
        'user_form': user_form,
        'profile_form': profile_form,
        'password_form': password_form,
        'fighter_form': fighter_form,
        'judge_form': judge_form,
    }
    return render(request, 'users/profile.html', context)