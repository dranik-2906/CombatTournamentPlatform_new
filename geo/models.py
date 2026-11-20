from django.db import models

class Country(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name='Страна')
    code = models.CharField(max_length=2, unique=True, verbose_name='Код страны (ISO)')

    class Meta:
        verbose_name = 'Страна'
        verbose_name_plural = 'Страны'
        ordering = ['name']

    def __str__(self):
        return self.name

class City(models.Model):
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='cities', verbose_name='Страна')
    name = models.CharField(max_length=100, verbose_name='Город')

    class Meta:
        verbose_name = 'Город'
        verbose_name_plural = 'Города'
        ordering = ['name']
        unique_together = ('country', 'name')

    def __str__(self):
        return f"{self.name}, {self.country.name}"