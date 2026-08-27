from django.db import models
from django.contrib.auth.models import User


class Judge(models.Model):
    JUDGE_CATEGORY_CHOICES = (
        ('1', 'Первая категория'),
        ('2', 'Вторая категория'),
        ('3', 'Третья категория'),
        ('b', 'Всероссийская категория'),
        ('i', 'Международная категория'),
    )

    JUDGE_TYPE_CHOICES = (
        ('referee', 'Рефери'),
        ('side', 'Боковой судья'),
        ('head', 'Главный судья'),
    )

    user = models.OneToOneField(
        User, on_delete=models.CASCADE,
        related_name='judge', verbose_name='Пользователь'
    )
    first_name = models.CharField(max_length=100, verbose_name='Имя')
    last_name = models.CharField(max_length=100, verbose_name='Фамилия')
    category = models.CharField(
        max_length=2, choices=JUDGE_CATEGORY_CHOICES, verbose_name='Категория'
    )
    judge_type = models.CharField(
        max_length=10, choices=JUDGE_TYPE_CHOICES, verbose_name='Тип судьи'
    )
    license_number = models.CharField(max_length=50, blank=True, verbose_name='Номер лицензии')
    experience_years = models.PositiveIntegerField(
        default=0, blank=True, null=True, verbose_name='Стаж (лет)'
    )
    is_active = models.BooleanField(default=True, verbose_name='Активный')

    class Meta:
        verbose_name = 'Судья'
        verbose_name_plural = 'Судьи'
        ordering = ['-is_active', 'last_name', 'first_name']

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.get_judge_type_display()})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def save(self, *args, **kwargs):
        if self.user:
            if self.first_name and not self.user.first_name:
                self.user.first_name = self.first_name
            if self.last_name and not self.user.last_name:
                self.user.last_name = self.last_name
            self.user.save()
        super().save(*args, **kwargs)
