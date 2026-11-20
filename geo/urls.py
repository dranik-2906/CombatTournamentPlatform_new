from django.urls import path
from . import views

urlpatterns = [
    path('api/cities/<int:country_id>/', views.get_cities, name='get_cities'),
]