from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models

phone_validator = RegexValidator(
    regex=r'^\+?\d{10,15}$',
    message='Enter a valid phone number (10-15 digits, optional leading +).',
)


class User(AbstractUser):
    class Role(models.TextChoices):
        COMPLAINANT = 'complainant', 'Complainant'
        STAFF = 'staff', 'Staff'
        ADMIN = 'admin', 'Admin'

    email = models.EmailField('email address', unique=True)
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.COMPLAINANT,
        db_index=True,
    )
    phone = models.CharField(max_length=16, blank=True, validators=[phone_validator])

    class Meta:
        ordering = ['username']

    def save(self, *args, **kwargs):
        self.email = self.email.lower()
        if self.is_superuser:
            self.role = self.Role.ADMIN
        if self.role == self.Role.ADMIN:
            self.is_staff = True
        super().save(*args, **kwargs)

    # NOTE: `is_staff` already exists on AbstractUser (Django admin access),
    # so role helpers use different names to avoid a clash.
    @property
    def is_complainant(self):
        return self.role == self.Role.COMPLAINANT

    @property
    def is_staff_member(self):
        return self.role == self.Role.STAFF

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN

    @property
    def is_support_team(self):
        return self.role in (self.Role.STAFF, self.Role.ADMIN)

    @property
    def display_name(self):
        return self.get_full_name() or self.username

    def __str__(self):
        return f'{self.display_name} ({self.get_role_display()})'