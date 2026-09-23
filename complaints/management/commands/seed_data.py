"""
Create demo categories, users and complaints for development.

    python manage.py seed_data
    python manage.py seed_data --complaints 40
    python manage.py seed_data --complaints 0        # only categories and users

Do NOT run this on a production database.
"""
import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.test.utils import override_settings
from django.utils import timezone

from accounts.models import User
from complaints.models import Category, Comment, Complaint, StatusHistory

CATEGORIES = [
    ('Product Quality', 'Damaged, expired or defective products'),
    ('Delivery Delay', 'Late or missed deliveries'),
    ('Billing & Payments', 'Wrong amounts, double charges, refunds'),
    ('Staff Behaviour', 'Rude or unprofessional conduct'),
    ('Service Quality', 'Poor or incomplete service'),
    ('Other', 'Anything that does not fit the categories above'),
]

# (username, role, first name, last name)
USERS = [
    ('admin_demo', User.Role.ADMIN, 'Anita', 'Sharma'),
    ('staff_ravi', User.Role.STAFF, 'Ravi', 'Kumar'),
    ('staff_meera', User.Role.STAFF, 'Meera', 'Iyer'),
    ('user_asha', User.Role.COMPLAINANT, 'Asha', 'Patel'),
    ('user_kabir', User.Role.COMPLAINANT, 'Kabir', 'Singh'),
    ('user_neha', User.Role.COMPLAINANT, 'Neha', 'Verma'),
]

SAMPLES = [
    ('Package arrived damaged', 'The outer box was crushed and two items inside were broken.', 'Product Quality'),
    ('Order delayed by a week', 'My order was promised in 3 days but has not arrived after 10 days.', 'Delivery Delay'),
    ('Charged twice for one order', 'The amount was debited two times from my account.', 'Billing & Payments'),
    ('Rude behaviour on the phone', 'The support agent spoke rudely and hung up on me.', 'Staff Behaviour'),
    ('Item expired before delivery', 'The product I received was already past its expiry date.', 'Product Quality'),
    ('Refund not received', 'I returned the item 3 weeks ago and the refund is still pending.', 'Billing & Payments'),
    ('Wrong item delivered', 'I ordered a blue one but received a red one.', 'Product Quality'),
    ('Nobody answers my calls', 'I have tried the helpline five times and nobody picks up.', 'Service Quality'),
    ('Delivery person left it outside', 'The parcel was left on the road instead of being handed over.', 'Delivery Delay'),
    ('Invoice has the wrong GST number', 'Please correct the GST number on my invoice.', 'Billing & Payments'),
]

STATUS_POOL = (
    [Complaint.Status.OPEN] * 3
    + [Complaint.Status.IN_PROGRESS] * 3
    + [Complaint.Status.RESOLVED] * 2
    + [Complaint.Status.CLOSED]
)


class Command(BaseCommand):
    help = 'Create demo categories, users and complaints for development.'

    def add_arguments(self, parser):
        parser.add_argument('--complaints', type=int, default=20,
                            help='How many sample complaints to create (default 20).')
        parser.add_argument('--password', default='Demo@12345',
                            help='Password for the demo users (default Demo@12345).')

    def handle(self, *args, **options):
        # Keep the terminal quiet: don't print an e-mail for every seeded event.
        with override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'):
            categories = self._create_categories()
            users = self._create_users(options['password'])
            count = options['complaints']
            if count > 0:
                self._create_complaints(count, categories, users)

        self.stdout.write(self.style.SUCCESS('Demo data ready.'))
        self.stdout.write(f'Demo users (password: {options["password"]}):')
        for username, role, *_ in USERS:
            self.stdout.write(f'  {username:<12} {role}')

    # ------------------------------------------------------------------
    def _create_categories(self):
        categories = {}
        for name, description in CATEGORIES:
            category, _ = Category.objects.get_or_create(
                name=name, defaults={'description': description}
            )
            categories[name] = category
        return categories

    def _create_users(self, password):
        users = {}
        for username, role, first, last in USERS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'email': f'{username}@example.com',
                    'first_name': first,
                    'last_name': last,
                    'role': role,
                },
            )
            if created:
                user.set_password(password)
                user.save()
            users[username] = user
        return users

    def _create_complaints(self, count, categories, users):
        complainants = [u for u in users.values() if u.role == User.Role.COMPLAINANT]
        handlers = [u for u in users.values() if u.role == User.Role.STAFF]
        now = timezone.now()

        for _ in range(count):
            title, description, category_name = random.choice(SAMPLES)
            created_at = now - timedelta(days=random.randint(0, 45), hours=random.randint(0, 23))

            complaint = Complaint.objects.create(
                title=title,
                description=description,
                category=categories[category_name],
                priority=random.choice(list(Complaint.Priority.values)),
                complainant=random.choice(complainants),
            )

            status = random.choice(STATUS_POOL)
            if status != Complaint.Status.OPEN or random.random() < 0.3:
                handler = random.choice(handlers)
                complaint.assigned_to = handler
                complaint.status = status
                complaint._changed_by = handler
                complaint._status_note = 'Seeded demo data'
                complaint.save()

                Comment.objects.create(
                    complaint=complaint, author=handler,
                    message='Thanks for reporting this. We are looking into it.',
                )
                Comment.objects.create(
                    complaint=complaint, author=handler, is_internal=True,
                    message='Internal: checked with the warehouse team.',
                )

            # Spread the data over the last weeks so dashboard charts look real
            updates = {'created_at': created_at}
            if complaint.status in (Complaint.Status.RESOLVED, Complaint.Status.CLOSED):
                updates['resolved_at'] = min(now, created_at + timedelta(days=random.randint(1, 5)))
            Complaint.objects.filter(pk=complaint.pk).update(**updates)

            for offset, entry in enumerate(complaint.history.order_by('id')):
                StatusHistory.objects.filter(pk=entry.pk).update(
                    changed_at=created_at + timedelta(hours=offset * 3)
                )

        self.stdout.write(f'Created {count} sample complaints.')