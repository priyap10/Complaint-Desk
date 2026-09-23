from django.test import TestCase
from django.urls import reverse

from .forms import RegistrationForm
from .models import User


class UserModelTests(TestCase):
    def test_default_role_is_complainant(self):
        user = User.objects.create_user('asha', 'asha@example.com', 'StrongPass#2024')
        self.assertEqual(user.role, User.Role.COMPLAINANT)
        self.assertFalse(user.is_support_team)

    def test_superuser_becomes_admin(self):
        user = User.objects.create_superuser('root', 'root@example.com', 'StrongPass#2024')
        self.assertEqual(user.role, User.Role.ADMIN)
        self.assertTrue(user.is_staff)

    def test_email_is_lowercased(self):
        user = User.objects.create_user('ravi', 'Ravi@Example.COM', 'StrongPass#2024')
        self.assertEqual(user.email, 'ravi@example.com')


class RegistrationTests(TestCase):
    def _payload(self, **overrides):
        data = {
            'username': 'newuser',
            'first_name': 'New',
            'last_name': 'User',
            'email': 'new@example.com',
            'phone': '9876543210',
            'password1': 'StrongPass#2024',
            'password2': 'StrongPass#2024',
        }
        data.update(overrides)
        return data

    def test_registration_creates_complainant(self):
        response = self.client.post(reverse('accounts:register'), self._payload())
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username='newuser')
        self.assertEqual(user.role, User.Role.COMPLAINANT)

    def test_role_cannot_be_injected(self):
        self.client.post(reverse('accounts:register'), self._payload(role='admin'))
        self.assertEqual(User.objects.get(username='newuser').role, User.Role.COMPLAINANT)

    def test_duplicate_email_rejected(self):
        User.objects.create_user('existing', 'new@example.com', 'StrongPass#2024')
        form = RegistrationForm(self._payload())
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)