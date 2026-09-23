"""
Helpers for the complaints app: ticket IDs, upload validation and
e-mail notifications.
"""
import logging
import os
import string

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import get_random_string

logger = logging.getLogger(__name__)

TICKET_ALPHABET = string.ascii_uppercase + string.digits


# ---------------------------------------------------------------------------
# Ticket IDs
# ---------------------------------------------------------------------------
def generate_ticket_id():
    """Return a unique ticket ID such as CMP-20260921-A7K2."""
    Complaint = apps.get_model('complaints', 'Complaint')
    prefix = f'CMP-{timezone.localdate():%Y%m%d}'
    while True:
        ticket = f'{prefix}-{get_random_string(4, TICKET_ALPHABET)}'
        if not Complaint.objects.filter(ticket_id=ticket).exists():
            return ticket


# ---------------------------------------------------------------------------
# Upload validation (used by the Attachment model field and the forms)
# ---------------------------------------------------------------------------
def validate_attachment(file):
    extension = os.path.splitext(file.name)[1].lower()
    allowed = settings.ALLOWED_ATTACHMENT_EXTENSIONS
    if extension not in allowed:
        raise ValidationError(
            f'"{extension or "no extension"}" files are not allowed. '
            f'Allowed types: {", ".join(allowed)}.'
        )

    max_bytes = settings.MAX_ATTACHMENT_SIZE_MB * 1024 * 1024
    if file.size > max_bytes:
        raise ValidationError(
            f'"{file.name}" is too large. Maximum size is {settings.MAX_ATTACHMENT_SIZE_MB} MB.'
        )


# ---------------------------------------------------------------------------
# E-mail notifications
# ---------------------------------------------------------------------------
def _site_url():
    # Optionally add SITE_URL = 'https://your-domain.com' to settings.py
    return getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000').rstrip('/')


def _link(complaint):
    return f"{_site_url()}{reverse('complaints:detail', args=[complaint.pk])}"


def _body(name, lines):
    return '\n'.join([f'Hi {name},', '', *lines, '', 'Regards,', 'Complaint Support Team'])


def _send(subject, body, recipients):
    recipients = [email for email in recipients if email]
    if not recipients:
        return
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=False)
    except Exception:  # never let a mail problem break a request
        logger.exception('Could not send e-mail "%s"', subject)


def send_complaint_created_email(complaint):
    user = complaint.complainant
    body = _body(user.display_name, [
        'We have received your complaint. Our team will look into it shortly.',
        '',
        f'Ticket ID : {complaint.ticket_id}',
        f'Title     : {complaint.title}',
        f'Category  : {complaint.category}',
        f'Priority  : {complaint.get_priority_display()}',
        '',
        'You can track its progress here:',
        _link(complaint),
    ])
    _send(f'[{complaint.ticket_id}] We received your complaint', body, [user.email])


def send_admin_alert_email(complaint):
    User = get_user_model()
    admins = User.objects.filter(role=User.Role.ADMIN, is_active=True)
    for admin in admins:
        body = _body(admin.display_name, [
            'A new complaint has been submitted.',
            '',
            f'Ticket ID  : {complaint.ticket_id}',
            f'Title      : {complaint.title}',
            f'Category   : {complaint.category}',
            f'Priority   : {complaint.get_priority_display()}',
            f'Submitted by: {complaint.complainant.display_name}',
            '',
            _link(complaint),
        ])
        _send(f'[{complaint.ticket_id}] New complaint: {complaint.title}', body, [admin.email])


def notify_new_complaint(complaint):
    send_complaint_created_email(complaint)
    send_admin_alert_email(complaint)


def send_status_change_email(complaint, old_status):
    user = complaint.complainant
    old_label = complaint.Status(old_status).label if old_status in complaint.Status.values else old_status
    body = _body(user.display_name, [
        f'The status of your complaint {complaint.ticket_id} has changed.',
        '',
        f'Previous status : {old_label}',
        f'New status      : {complaint.get_status_display()}',
        '',
        'View the details here:',
        _link(complaint),
    ])
    _send(f'[{complaint.ticket_id}] Status updated: {complaint.get_status_display()}', body, [user.email])


def send_assignment_email(complaint):
    assignee = complaint.assigned_to
    if not assignee:
        return
    body = _body(assignee.display_name, [
        'A complaint has been assigned to you.',
        '',
        f'Ticket ID : {complaint.ticket_id}',
        f'Title     : {complaint.title}',
        f'Priority  : {complaint.get_priority_display()}',
        '',
        _link(complaint),
    ])
    _send(f'[{complaint.ticket_id}] Assigned to you', body, [assignee.email])


def send_comment_email(comment):
    """Tell the other side of the conversation about a new public comment."""
    complaint = comment.complaint
    author = comment.author
    if author is not None and author.pk == complaint.complainant_id:
        recipient = complaint.assigned_to      # complainant wrote -> notify assignee
    else:
        recipient = complaint.complainant      # staff wrote -> notify complainant
    if recipient is None:
        return
    who = author.display_name if author else 'Someone'
    body = _body(recipient.display_name, [
        f'{who} added a comment on complaint {complaint.ticket_id}:',
        '',
        comment.message,
        '',
        _link(complaint),
    ])
    _send(f'[{complaint.ticket_id}] New comment', body, [recipient.email])