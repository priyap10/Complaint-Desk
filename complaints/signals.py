"""
Signals keep the status history, notifications and uploaded files in sync.

Views tell the signals *who* made a change by setting two optional
attributes on the complaint before saving:

    complaint._changed_by = request.user
    complaint._status_note = 'Waiting for the courier'
"""
from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import Attachment, Comment, Complaint, StatusHistory
from .utils import (
    notify_new_complaint,
    send_assignment_email,
    send_comment_email,
    send_status_change_email,
)


@receiver(pre_save, sender=Complaint)
def remember_previous_state(sender, instance, **kwargs):
    instance._old_status = None
    instance._old_assignee_id = None
    if instance.pk:
        previous = (
            Complaint.objects.filter(pk=instance.pk)
            .values('status', 'assigned_to_id')
            .first()
        )
        if previous:
            instance._old_status = previous['status']
            instance._old_assignee_id = previous['assigned_to_id']


@receiver(post_save, sender=Complaint)
def log_complaint_changes(sender, instance, created, **kwargs):
    actor = getattr(instance, '_changed_by', None)
    note = getattr(instance, '_status_note', '')
    instance._status_note = ''  # don't leak the note into later saves

    if created:
        StatusHistory.objects.create(
            complaint=instance,
            old_status='',
            new_status=instance.status,
            changed_by=actor or instance.complainant,
            note='Complaint submitted',
        )
        transaction.on_commit(lambda: notify_new_complaint(instance))
        return

    old_status = instance._old_status
    if old_status and old_status != instance.status:
        StatusHistory.objects.create(
            complaint=instance,
            old_status=old_status,
            new_status=instance.status,
            changed_by=actor,
            note=note,
        )
        transaction.on_commit(lambda: send_status_change_email(instance, old_status))

    if instance._old_assignee_id != instance.assigned_to_id:
        if instance.assigned_to_id:
            text = f'Assigned to {instance.assigned_to.display_name}'
        else:
            text = 'Unassigned'
        StatusHistory.objects.create(
            complaint=instance,
            old_status=instance.status,
            new_status=instance.status,
            changed_by=actor,
            note=text,
        )
        if instance.assigned_to_id:
            transaction.on_commit(lambda: send_assignment_email(instance))


@receiver(post_save, sender=Comment)
def notify_on_comment(sender, instance, created, **kwargs):
    if created and not instance.is_internal:
        transaction.on_commit(lambda: send_comment_email(instance))


@receiver(post_delete, sender=Attachment)
def delete_attachment_file(sender, instance, **kwargs):
    """Remove the file from disk when its database row is deleted."""
    if instance.file:
        instance.file.delete(save=False)