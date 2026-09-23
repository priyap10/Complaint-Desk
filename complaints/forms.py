from django import forms
from django.conf import settings
from django.db.models import Q

from accounts.forms import BootstrapFormMixin
from accounts.models import User

from .models import Attachment, Category, Comment, Complaint
from .utils import validate_attachment

MAX_FILES_PER_UPLOAD = 5


# ---------------------------------------------------------------------------
# Multiple-file upload field (Django needs a small custom field for this)
# ---------------------------------------------------------------------------
class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('widget', MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_file_clean(item, initial) for item in data]
        return [single_file_clean(data, initial)] if data else []


# ---------------------------------------------------------------------------
# Complainant forms
# ---------------------------------------------------------------------------
class ComplaintForm(BootstrapFormMixin, forms.ModelForm):
    """Used to file a new complaint and to edit an open one."""

    attachments = MultipleFileField(required=False, validators=[validate_attachment])

    class Meta:
        model = Complaint
        fields = ('title', 'category', 'priority', 'description')
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'Short summary of the problem'}),
            'description': forms.Textarea(
                attrs={'rows': 6, 'placeholder': 'Describe what happened, when, and what you expect.'}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        categories = Category.objects.filter(is_active=True)
        if self.instance.pk and self.instance.category_id:
            # keep the current category selectable even if it was deactivated later
            categories = Category.objects.filter(
                Q(is_active=True) | Q(pk=self.instance.category_id)
            )
        self.fields['category'].queryset = categories
        self.fields['category'].empty_label = 'Select a category'

        allowed = ', '.join(settings.ALLOWED_ATTACHMENT_EXTENSIONS)
        self.fields['attachments'].help_text = (
            f'Optional. Up to {MAX_FILES_PER_UPLOAD} files, '
            f'{settings.MAX_ATTACHMENT_SIZE_MB} MB each. Allowed: {allowed}'
        )

    def clean_attachments(self):
        files = self.cleaned_data.get('attachments') or []
        if len(files) > MAX_FILES_PER_UPLOAD:
            raise forms.ValidationError(
                f'You can upload at most {MAX_FILES_PER_UPLOAD} files at a time.'
            )
        return files

    def save_attachments(self, complaint, user):
        """Call after the complaint has been saved."""
        for uploaded in self.cleaned_data.get('attachments', []):
            Attachment.objects.create(complaint=complaint, file=uploaded, uploaded_by=user)


class CommentForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Comment
        fields = ('message', 'is_internal')
        labels = {'message': 'Add a comment', 'is_internal': 'Internal note (hidden from the complainant)'}
        widgets = {'message': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Write your message...'})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is None or not user.is_support_team:
            del self.fields['is_internal']


# ---------------------------------------------------------------------------
# Staff / admin forms
# ---------------------------------------------------------------------------
class ComplaintManageForm(BootstrapFormMixin, forms.ModelForm):
    """Status / priority / assignment. Only admins can change the assignee."""

    note = forms.CharField(
        required=False,
        max_length=255,
        label='Note (optional)',
        widget=forms.TextInput(attrs={'placeholder': 'Reason for this update'}),
    )

    class Meta:
        model = Complaint
        fields = ('status', 'priority', 'assigned_to')

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user.is_admin_role:
            field = self.fields['assigned_to']
            field.queryset = User.objects.filter(
                role__in=[User.Role.STAFF, User.Role.ADMIN], is_active=True
            ).order_by('username')
            field.required = False
            field.empty_label = 'Unassigned'
            field.label_from_instance = lambda u: f'{u.display_name} ({u.get_role_display()})'
        else:
            del self.fields['assigned_to']


class ComplaintFilterForm(BootstrapFormMixin, forms.Form):
    """GET-based search and filter bar for the complaint lists."""

    q = forms.CharField(
        required=False,
        label='Search',
        widget=forms.TextInput(attrs={'placeholder': 'Ticket ID, title or complainant'}),
    )
    status = forms.ChoiceField(
        required=False, choices=[('', 'All statuses')] + Complaint.Status.choices
    )
    priority = forms.ChoiceField(
        required=False, choices=[('', 'All priorities')] + Complaint.Priority.choices
    )
    category = forms.ModelChoiceField(
        queryset=Category.objects.all(), required=False, empty_label='All categories'
    )
    assigned = forms.ChoiceField(
        required=False,
        choices=[('', 'Anyone'), ('me', 'Assigned to me'), ('unassigned', 'Unassigned')],
    )

    def __init__(self, *args, support=True, **kwargs):
        super().__init__(*args, **kwargs)
        if not support:
            del self.fields['assigned']