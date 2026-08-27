from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from core.views import home   # импорт представления для главной страницы

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home, name='home'),  # глобальное имя 'home' для шаблонов
    path('', include('core.urls', namespace='core')),
    path('users/', include('users.urls', namespace='users')),
    path('tournaments/', include('tournaments.urls', namespace='tournaments')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)