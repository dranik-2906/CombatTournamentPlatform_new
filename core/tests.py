from django.test import TestCase, Client
from django.contrib.auth.models import User


class CoreTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_home_page(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

    def test_dashboard_redirects_for_anonymous(self):
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 302)

    def test_dashboard_access_for_authenticated(self):
        user = User.objects.create_user(username='test', password='testpass')
        self.client.login(username='test', password='testpass')
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
