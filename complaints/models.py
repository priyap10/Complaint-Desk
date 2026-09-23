import os

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from .utils import generate_ticket_id, validate_attachment


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(
        default=True,
        help_text='Untick to hide this category from new complaints without deleting it.',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'categories'

    def __str__(self):
        return self.name


class ComplaintQuerySet(models.QuerySet):
    def visible_to(self, user):
        """Only return the complaints this user is allowed to see."""
        if not user.is_authenticated:
            return self.none()
        if user.is_admin_role:
            return self
        if user.is_staff_member:
            # Their own queue: assigned to them, still unassigned, or filed by them
            return self.filter(
                Q(assigned_to=user) | Q(assigned_to__isnull=True) | Q(complainant=user)
            )
        return self.filter(complainant=user)

    def unresolved(self):
        return self.filter(status__in=[Complaint.Status.OPEN, Complaint.Status.IN_PROGRESS])


class Complaint(models.Model):
    class Status(models.TextChoices):
        OPEN = 'open', 'Open'
        IN_PROGRESS = 'in_progress', 'In Progress'
        RESOLVED = 'resolved', 'Resolved'
        CLOSED = 'closed', 'Closed'

    class Priority(models.TextChoices):
        LOW = 'low', 'Low'
        MEDIUM = 'medium', 'Medium'
        HIGH = 'high', 'High'
        URGENT = 'urgent', 'Urgent'

    ticket_id = models.CharField(max_length=20, unique=True, editable=False)
    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='complaints')
    priority = models.CharField(
        max_length=10, choices=Priority.choices, default=Priority.MEDIUM, db_index=True
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True
    )
    complainant = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='complaints'
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_complaints',
        limit_choices_to={'role__in': ['staff', 'admin']},
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True, editable=False)

    objects = ComplaintQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.ticket_id} - {self.title}'

    def get_absolute_url(self):
        return reverse('complaints:detail', args=[self.pk])

    def save(self, *args, **kwargs):
        if not self.ticket_id:
            self.ticket_id = generate_ticket_id()
        if self.status in (self.Status.RESOLVED, self.Status.CLOSED):
            if self.resolved_at is None:
                self.resolved_at = timezone.now()
        else:
            self.resolved_at = None  # re-opened
        super().save(*args, **kwargs)

    # -- helpers used by templates -------------------------------------------
    @property
    def status_badge(self):
        """Bootstrap colour name for the status badge."""
        return {
            self.Status.OPEN: 'danger',
            self.Status.IN_PROGRESS: 'warning',
            self.Status.RESOLVED: 'success',
            self.Status.CLOSED: 'secondary',
        }.get(self.status, 'secondary')

    @property
    def priority_badge(self):
        """Bootstrap colour name for the priority badge."""
        return {
            self.Priority.LOW: 'secondary',
            self.Priority.MEDIUM: 'info',
            self.Priority.HIGH: 'warning',
            self.Priority.URGENT: 'danger',
        }.get(self.priority, 'secondary')

    @property
    def accepts_comments(self):
        return self.status != self.Status.CLOSED

    # -- permission rules ----------------------------------------------------
    def can_be_edited_by(self, user):
        """Owners may edit a complaint until work on it starts."""
        return self.complainant_id == user.pk and self.status == self.Status.OPEN

    def can_be_deleted_by(self, user):
        return user.is_admin_role or self.can_be_edited_by(user)

    def can_be_claimed_by(self, user):
        return (
            user.is_staff_member
            and self.assigned_to_id is None
            and self.complainant_id != user.pk
            and self.status != self.Status.CLOSED
        )


class Comment(models.Model):
    complaint = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='complaint_comments',
    )
    message = models.TextField()
    is_internal = models.BooleanField(
        default=False,
        help_text='Internal notes are visible to staff and admins only.',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'Comment on {self.complaint.ticket_id} by {self.author}'


class Attachment(models.Model):
    complaint = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(
        upload_to='complaint_attachments/%Y/%m/', validators=[validate_attachment]
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['uploaded_at']

    def __str__(self):
        return self.filename

    @property
    def filename(self):
        return os.path.basename(self.file.name)

    @property
    def is_image(self):
        return os.path.splitext(self.file.name)[1].lower() in ('.jpg', '.jpeg', '.png')


class StatusHistory(models.Model):
    """
    Timeline of a complaint. A row with old_status != new_status is a status
    change; a row where both are equal is a note (e.g. an assignment).
    """

    complaint = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name='history')
    old_status = models.CharField(max_length=20, choices=Complaint.Status.choices, blank=True)
    new_status = models.CharField(max_length=20, choices=Complaint.Status.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    note = models.CharField(max_length=255, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['changed_at', 'id']
        verbose_name_plural = 'status history'

    def __str__(self):
        return f'{self.complaint.ticket_id}: {self.old_status or "-"} -> {self.new_status}'