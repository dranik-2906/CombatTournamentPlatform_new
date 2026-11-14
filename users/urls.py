from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register, name='register'),
    path('federations/', views.federation_list, name='federation_list'),
    path('federations/create/', views.create_federation, name='federation_create'),
]
