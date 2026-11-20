from django.http import JsonResponse
from .models import City

def get_cities(request, country_id):
    cities = City.objects.filter(country_id=country_id).values('id', 'name')
    return JsonResponse({'cities': list(cities)})