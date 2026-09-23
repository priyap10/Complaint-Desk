from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from accounts.models import User

from .models import Category, Comment, Complaint
from .utils import validate_attachment

PASSWORD = 'StrongPass#2024'


class BaseTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user('admin1', 'admin1@example.com', PASSWORD, role=User.Role.ADMIN)
        cls.staff = User.objects.create_user('staff1', 'staff1@example.com', PASSWORD, role=User.Role.STAFF)
        cls.other_staff = User.objects.create_user('staff2', 'staff2@example.com', PASSWORD, role=User.Role.STAFF)
        cls.user = User.objects.create_user('user1', 'user1@example.com', PASSWORD)
        cls.other_user = User.objects.create_user('user2', 'user2@example.com', PASSWORD)
        cls.category = Category.objects.create(name='Delivery')

    def make_complaint(self, **kwargs):
        data = {
            'title': 'Late delivery',
            'description': 'The order arrived three days late.',
            'category': self.category,
            'complainant': self.user,
        }
        data.update(kwargs)
        return Complaint.objects.create(**data)


class ComplaintModelTests(BaseTestCase):
    def test_ticket_id_format(self):
        complaint = self.make_complaint()
        self.assertRegex(complaint.ticket_id, r'^CMP-\d{8}-[A-Z0-9]{4}$')

    def test_ticket_ids_are_unique(self):
        ids = {self.make_complaint().ticket_id for _ in range(20)}
        self.assertEqual(len(ids), 20)

    def test_creation_writes_first_history_entry(self):
        complaint = self.make_complaint()
        entry = complaint.history.get()
        self.assertEqual(entry.new_status, Complaint.Status.OPEN)
        self.assertEqual(entry.changed_by, self.user)

    def test_status_change_is_logged_with_actor_and_note(self):
        complaint = self.make_complaint()
        complaint.status = Complaint.Status.IN_PROGRESS
        complaint._changed_by = self.staff
        complaint._status_note = 'Contacted the courier'
        complaint.save()

        entry = complaint.history.filter(new_status=Complaint.Status.IN_PROGRESS).get()
        self.assertEqual(entry.old_status, Complaint.Status.OPEN)
        self.assertEqual(entry.changed_by, self.staff)
        self.assertEqual(entry.note, 'Contacted the courier')

    def test_assignment_is_logged(self):
        complaint = self.make_complaint()
        complaint.assigned_to = self.staff
        complaint._changed_by = self.admin
        complaint.save()
        self.assertTrue(complaint.history.filter(note__startswith='Assigned to').exists())

    def test_resolved_at_is_set_and_cleared(self):
        complaint = self.make_complaint()
        complaint.status = Complaint.Status.RESOLVED
        complaint.save()
        self.assertIsNotNone(complaint.resolved_at)

        complaint.status = Complaint.Status.IN_PROGRESS
        complaint.save()
        self.assertIsNone(complaint.resolved_at)


class VisibilityTests(BaseTestCase):
    def setUp(self):
        self.mine = self.make_complaint(title='Mine')
        self.others = self.make_complaint(title='Not mine', complainant=self.other_user)
        self.assigned_elsewhere = self.make_complaint(
            title='Handled by staff2', complainant=self.other_user, assigned_to=self.other_staff
        )

    def titles(self, user):
        return set(Complaint.objects.visible_to(user).values_list('title', flat=True))

    def test_complainant_sees_only_own(self):
        self.assertEqual(self.titles(self.user), {'Mine'})

    def test_staff_sees_unassigned_and_own_queue_only(self):
        self.assertEqual(self.titles(self.staff), {'Mine', 'Not mine'})
        self.assertEqual(self.titles(self.other_staff), {'Mine', 'Not mine', 'Handled by staff2'})

    def test_admin_sees_everything(self):
        self.assertEqual(self.titles(self.admin), {'Mine', 'Not mine', 'Handled by staff2'})


class NotificationTests(BaseTestCase):
    def test_new_complaint_emails_complainant_and_admin(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.make_complaint()
        recipients = [m.to for m in mail.outbox]
        self.assertIn([self.user.email], recipients)
        self.assertIn([self.admin.email], recipients)

    def test_status_change_emails_complainant(self):
        complaint = self.make_complaint()
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            complaint.status = Complaint.Status.RESOLVED
            complaint._changed_by = self.staff
            complaint.save()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])

    def test_internal_comment_sends_no_email(self):
        complaint = self.make_complaint(assigned_to=self.staff)
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            Comment.objects.create(complaint=complaint, author=self.staff, message='note', is_internal=True)
        self.assertEqual(len(mail.outbox), 0)


class ViewActionTests(BaseTestCase):
    """POST actions that redirect (no page rendering needed)."""

    def test_staff_can_claim_unassigned_complaint(self):
        complaint = self.make_complaint()
        self.client.force_login(self.staff)
        response = self.client.post(reverse('complaints:claim', args=[complaint.pk]))
        self.assertEqual(response.status_code, 302)
        complaint.refresh_from_db()
        self.assertEqual(complaint.assigned_to, self.staff)
        self.assertEqual(complaint.status, Complaint.Status.IN_PROGRESS)

    def test_admin_can_resolve_and_assign(self):
        complaint = self.make_complaint()
        self.client.force_login(self.admin)
        self.client.post(reverse('complaints:manage', args=[complaint.pk]), {
            'status': 'resolved', 'priority': 'high',
            'assigned_to': self.staff.pk, 'note': 'Refund issued',
        })
        complaint.refresh_from_db()
        self.assertEqual(complaint.status, Complaint.Status.RESOLVED)
        self.assertEqual(complaint.priority, Complaint.Priority.HIGH)
        self.assertEqual(complaint.assigned_to, self.staff)
        self.assertTrue(complaint.history.filter(note='Refund issued').exists())

    def test_staff_updating_unassigned_complaint_takes_it(self):
        complaint = self.make_complaint()
        self.client.force_login(self.staff)
        self.client.post(reverse('complaints:manage', args=[complaint.pk]), {
            'status': 'in_progress', 'priority': 'medium',
        })
        complaint.refresh_from_db()
        self.assertEqual(complaint.assigned_to, self.staff)

    def test_complainant_cannot_make_internal_comments(self):
        complaint = self.make_complaint()
        self.client.force_login(self.user)
        self.client.post(reverse('complaints:comment', args=[complaint.pk]),
                         {'message': 'Any update?', 'is_internal': 'on'})
        comment = Comment.objects.get(complaint=complaint)
        self.assertFalse(comment.is_internal)

    def test_comments_blocked_on_closed_complaint(self):
        complaint = self.make_complaint(status=Complaint.Status.CLOSED)
        self.client.force_login(self.user)
        self.client.post(reverse('complaints:comment', args=[complaint.pk]), {'message': 'Hello?'})
        self.assertEqual(complaint.comments.count(), 0)


class AttachmentValidationTests(TestCase):
    def test_rejects_disallowed_extension(self):
        with self.assertRaises(ValidationError):
            validate_attachment(SimpleUploadedFile('virus.exe', b'data'))

    def test_rejects_oversized_file(self):
        big = SimpleUploadedFile('big.pdf', b'x' * (5 * 1024 * 1024 + 1))
        with self.assertRaises(ValidationError):
            validate_attachment(big)

    def test_accepts_valid_file(self):
        validate_attachment(SimpleUploadedFile('photo.jpg', b'data'))