from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import STAFF_ONLY, SUPPORT_TEAM, role_required

from .forms import (
    CommentForm,
    ComplaintFilterForm,
    ComplaintForm,
    ComplaintManageForm,
)
from .models import Attachment, Complaint

LIST_RELATED = ('category', 'complainant', 'assigned_to')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _paginate(request, queryset):
    paginator = Paginator(queryset, settings.COMPLAINTS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)
    return page_obj, params.urlencode()  # querystring keeps filters when paging


def _apply_filters(queryset, form, user):
    if not form.is_valid():
        return queryset
    data = form.cleaned_data

    term = (data.get('q') or '').strip()
    if term:
        queryset = queryset.filter(
            Q(ticket_id__icontains=term)
            | Q(title__icontains=term)
            | Q(complainant__username__icontains=term)
            | Q(complainant__first_name__icontains=term)
            | Q(complainant__last_name__icontains=term)
        )
    if data.get('status'):
        queryset = queryset.filter(status=data['status'])
    if data.get('priority'):
        queryset = queryset.filter(priority=data['priority'])
    if data.get('category'):
        queryset = queryset.filter(category=data['category'])
    if data.get('assigned') == 'me':
        queryset = queryset.filter(assigned_to=user)
    elif data.get('assigned') == 'unassigned':
        queryset = queryset.filter(assigned_to__isnull=True)
    return queryset


def _visible_complaint_or_404(user, pk):
    return get_object_or_404(Complaint.objects.visible_to(user).select_related(*LIST_RELATED), pk=pk)


# ---------------------------------------------------------------------------
# Lists
# ---------------------------------------------------------------------------
@role_required(*SUPPORT_TEAM)
def complaint_list(request):
    """All complaints a staff member or admin can work on."""
    form = ComplaintFilterForm(request.GET)
    queryset = Complaint.objects.visible_to(request.user).select_related(*LIST_RELATED)
    queryset = _apply_filters(queryset, form, request.user)
    page_obj, querystring = _paginate(request, queryset)
    return render(request, 'complaints/complaint_list.html', {
        'form': form,
        'page_obj': page_obj,
        'querystring': querystring,
    })


@login_required
def my_complaints(request):
    """Complaints filed by the logged-in user."""
    form = ComplaintFilterForm(request.GET, support=False)
    queryset = Complaint.objects.filter(complainant=request.user).select_related(
        'category', 'assigned_to'
    )
    queryset = _apply_filters(queryset, form, request.user)
    page_obj, querystring = _paginate(request, queryset)
    return render(request, 'complaints/my_complaints.html', {
        'form': form,
        'page_obj': page_obj,
        'querystring': querystring,
    })


# ---------------------------------------------------------------------------
# Create / read / update / delete
# ---------------------------------------------------------------------------
@login_required
def complaint_create(request):
    if request.method == 'POST':
        form = ComplaintForm(request.POST, request.FILES)
        if form.is_valid():
            complaint = form.save(commit=False)
            complaint.complainant = request.user
            complaint._changed_by = request.user
            complaint.save()
            form.save_attachments(complaint, request.user)
            messages.success(
                request, f'Complaint submitted. Your ticket ID is {complaint.ticket_id}.'
            )
            return redirect(complaint)
    else:
        form = ComplaintForm()

    return render(request, 'complaints/complaint_form.html', {'form': form, 'is_edit': False})


@login_required
def complaint_detail(request, pk):
    complaint = _visible_complaint_or_404(request.user, pk)
    user = request.user

    comments = complaint.comments.select_related('author')
    if not user.is_support_team:
        comments = comments.filter(is_internal=False)  # hide internal notes

    context = {
        'complaint': complaint,
        'comments': comments,
        'attachments': complaint.attachments.select_related('uploaded_by'),
        'history': complaint.history.select_related('changed_by'),
        'comment_form': CommentForm(user=user),
        'manage_form': (
            ComplaintManageForm(instance=complaint, user=user) if user.is_support_team else None
        ),
        'can_edit': complaint.can_be_edited_by(user),
        'can_delete': complaint.can_be_deleted_by(user),
        'can_claim': complaint.can_be_claimed_by(user),
    }
    return render(request, 'complaints/complaint_detail.html', context)


@login_required
def complaint_edit(request, pk):
    complaint = get_object_or_404(Complaint, pk=pk, complainant=request.user)
    if not complaint.can_be_edited_by(request.user):
        messages.error(request, 'Only open complaints can be edited.')
        return redirect(complaint)

    if request.method == 'POST':
        form = ComplaintForm(request.POST, request.FILES, instance=complaint)
        if form.is_valid():
            complaint = form.save()
            form.save_attachments(complaint, request.user)
            messages.success(request, 'Your complaint has been updated.')
            return redirect(complaint)
    else:
        form = ComplaintForm(instance=complaint)

    return render(request, 'complaints/complaint_form.html', {
        'form': form,
        'complaint': complaint,
        'attachments': complaint.attachments.all(),
        'is_edit': True,
    })


@login_required
def complaint_delete(request, pk):
    complaint = _visible_complaint_or_404(request.user, pk)
    if not complaint.can_be_deleted_by(request.user):
        messages.error(request, 'You cannot delete this complaint.')
        return redirect(complaint)

    if request.method == 'POST':
        ticket_id = complaint.ticket_id
        complaint.delete()
        messages.success(request, f'Complaint {ticket_id} was deleted.')
        return redirect('accounts:home')

    return render(request, 'complaints/complaint_confirm_delete.html', {'complaint': complaint})


# ---------------------------------------------------------------------------
# Actions (POST only)
# ---------------------------------------------------------------------------
@require_POST
@login_required
def add_comment(request, pk):
    complaint = _visible_complaint_or_404(request.user, pk)
    if not complaint.accepts_comments:
        messages.warning(request, 'This complaint is closed, so new comments are disabled.')
        return redirect(complaint)

    form = CommentForm(request.POST, user=request.user)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.complaint = complaint
        comment.author = request.user
        if not request.user.is_support_team:
            comment.is_internal = False
        comment.save()
        messages.success(request, 'Your comment has been added.')
    else:
        messages.error(request, 'Please write a message before posting.')
    return redirect(f'{complaint.get_absolute_url()}#comments')


@require_POST
@role_required(*SUPPORT_TEAM)
def manage_complaint(request, pk):
    """Staff/admin update status, priority and (admins only) assignment."""
    complaint = _visible_complaint_or_404(request.user, pk)
    form = ComplaintManageForm(request.POST, instance=complaint, user=request.user)

    if form.is_valid():
        complaint = form.save(commit=False)
        # Staff who work on an unassigned complaint automatically take it
        if request.user.is_staff_member and complaint.assigned_to_id is None:
            complaint.assigned_to = request.user
        complaint._changed_by = request.user
        complaint._status_note = form.cleaned_data.get('note', '')
        complaint.save()
        messages.success(request, 'Complaint updated.')
    else:
        messages.error(request, 'Could not update the complaint. Please check the form.')
    return redirect(complaint)


@require_POST
@role_required(*STAFF_ONLY)
def claim_complaint(request, pk):
    """A staff member picks up an unassigned complaint."""
    complaint = _visible_complaint_or_404(request.user, pk)
    if not complaint.can_be_claimed_by(request.user):
        messages.error(request, 'This complaint cannot be claimed.')
        return redirect(complaint)

    complaint.assigned_to = request.user
    if complaint.status == Complaint.Status.OPEN:
        complaint.status = Complaint.Status.IN_PROGRESS
    complaint._changed_by = request.user
    complaint._status_note = 'Picked up by staff'
    complaint.save()
    messages.success(request, f'You are now handling {complaint.ticket_id}.')
    return redirect(complaint)


@require_POST
@login_required
def attachment_delete(request, pk):
    attachment = get_object_or_404(
        Attachment.objects.select_related('complaint'),
        pk=pk,
        complaint__in=Complaint.objects.visible_to(request.user),
    )
    complaint = attachment.complaint
    if not complaint.can_be_deleted_by(request.user):
        messages.error(request, 'You cannot remove this attachment.')
        return redirect(complaint)

    attachment.delete()
    messages.success(request, 'Attachment removed.')
    if complaint.can_be_edited_by(request.user):
        return redirect('complaints:edit', pk=complaint.pk)
    return redirect(complaint)