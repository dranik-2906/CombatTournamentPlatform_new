from django.test import TestCase, Client
from django.contrib.auth.models import User
from .models import Profile


class UserTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser', password='testpass123', email='test@test.com'
        )

    def test_login(self):
        response = self.client.post('/users/login/', {
            'username': 'testuser', 'password': 'testpass123'
        })
        self.assertEqual(response.status_code, 302)

    def test_register(self):
        response = self.client.post('/users/register/', {
            'username': 'newuser',
            'password1': 'newpass123',
            'password2': 'newpass123',
            'email': 'new@test.com',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username='newuser').exists())
        user = User.objects.get(username='newuser')
        self.assertTrue(hasattr(user, 'profile'))
        self.assertEqual(user.profile.role, 'fighter')

    def test_logout(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get('/users/logout/')
        self.assertEqual(response.status_code, 302)

    def test_profile_created(self):
        """Profile auto-created via signal"""
        self.assertTrue(hasattr(self.user, 'profile'))
        self.assertIsNotNone(self.user.profile)
