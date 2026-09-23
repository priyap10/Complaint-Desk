import csv
from datetime import timedelta

from django.db.models import (
    Avg,
    Case,
    Count,
    DurationField,
    ExpressionWrapper,
    F,
    IntegerField,
    Q,
    When,
)
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from accounts.decorators import ADMIN_ONLY, STAFF_ONLY, role_required
from accounts.models import User
from complaints.models import Category, Complaint

TREND_DAYS = 30
ACTIVE = [Complaint.Status.OPEN, Complaint.Status.IN_PROGRESS]
FINISHED = [Complaint.Status.RESOLVED, Complaint.Status.CLOSED]
RELATED = ('category', 'complainant', 'assigned_to')

def _priority_rank():
    """Annotation that sorts urgent first, then high, medium, low."""
    return Case(
        When(priority=Complaint.Priority.URGENT, then=0),
        When(priority=Complaint.Priority.HIGH, then=1),
        When(priority=Complaint.Priority.MEDIUM, then=2),
        default=3,
        output_field=IntegerField(),
    )


def _counts(queryset, field):
    """{'open': 4, 'resolved': 2, ...} for the given field."""
    return dict(queryset.order_by().values_list(field).annotate(n=Count('id')))


def _chart(counts, choices):
    """Turn a counts dict into {'labels': [...], 'values': [...]} for Chart.js."""
    return {
        'labels': [label for _, label in choices],
        'values': [counts.get(value, 0) for value, _ in choices],
    }


def _daily_counts(queryset, field, start):
    rows = (
        queryset.filter(**{f'{field}__date__gte': start})
        .order_by()
        .annotate(day=TruncDate(field))
        .values('day')
        .annotate(n=Count('id'))
    )
    return {row['day']: row['n'] for row in rows}


def _trend(days=TREND_DAYS):
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    created = _daily_counts(Complaint.objects.all(), 'created_at', start)
    resolved = _daily_counts(Complaint.objects.filter(resolved_at__isnull=False), 'resolved_at', start)
    dates = [start + timedelta(days=i) for i in range(days)]
    return {
        'labels': [d.strftime('%d %b') for d in dates],
        'created': [created.get(d, 0) for d in dates],
        'resolved': [resolved.get(d, 0) for d in dates],
    }


def _average_resolution_days():
    duration = ExpressionWrapper(F('resolved_at') - F('created_at'), output_field=DurationField())
    average = Complaint.objects.filter(resolved_at__isnull=False).aggregate(avg=Avg(duration))['avg']
    if average is None:
        return None
    return round(average.total_seconds() / 86400, 1)
def get_admin_dashboard_data():
    complaints = Complaint.objects.all()
    unresolved = complaints.unresolved()
    status_counts = _counts(complaints, 'status')
    priority_counts = _counts(complaints, 'priority')

    categories = (
        Category.objects.annotate(total=Count('complaints'))
        .filter(total__gt=0)
        .order_by('-total', 'name')
    )

    staff_workload = (
        User.objects.filter(role=User.Role.STAFF, is_active=True)
        .annotate(
            active_count=Count('assigned_complaints', filter=Q(assigned_complaints__status__in=ACTIVE)),
            finished_count=Count('assigned_complaints', filter=Q(assigned_complaints__status__in=FINISHED)),
        )
        .order_by('-active_count', 'username')
    )

    needs_attention = (
        unresolved.filter(
            priority__in=[Complaint.Priority.HIGH, Complaint.Priority.URGENT],
            assigned_to__isnull=True,
        )
        .select_related(*RELATED)
        .annotate(rank=_priority_rank())
        .order_by('rank', 'created_at')[:5]
    )

    return {
        'stats': {
            'total': sum(status_counts.values()),
            'open': status_counts.get(Complaint.Status.OPEN.value, 0),
            'in_progress': status_counts.get(Complaint.Status.IN_PROGRESS.value, 0),
            'resolved': status_counts.get(Complaint.Status.RESOLVED.value, 0),
            'closed': status_counts.get(Complaint.Status.CLOSED.value, 0),
            'unassigned': unresolved.filter(assigned_to__isnull=True).count(),
            'urgent_open': unresolved.filter(priority=Complaint.Priority.URGENT).count(),
            'avg_resolution_days': _average_resolution_days(),
        },
        'status_chart': _chart(status_counts, Complaint.Status.choices),
        'priority_chart': _chart(priority_counts, Complaint.Priority.choices),
        'category_chart': {
            'labels': [c.name for c in categories],
            'values': [c.total for c in categories],
        },
        'trend_chart': _trend(),
        'trend_days': TREND_DAYS,
        'staff_workload': staff_workload,
        'needs_attention': needs_attention,
        'recent_complaints': complaints.select_related(*RELATED)[:8],
    }


def get_staff_dashboard_data(user):
    mine = Complaint.objects.filter(assigned_to=user)
    status_counts = _counts(mine, 'status')
    week_ago = timezone.now() - timedelta(days=7)

    pool = (
        Complaint.objects.unresolved()
        .filter(assigned_to__isnull=True)
        .exclude(complainant=user)
    )

    return {
        'stats': {
            'active': status_counts.get(Complaint.Status.OPEN.value, 0)
            + status_counts.get(Complaint.Status.IN_PROGRESS.value, 0),
            'open': status_counts.get(Complaint.Status.OPEN.value, 0),
            'in_progress': status_counts.get(Complaint.Status.IN_PROGRESS.value, 0),
            'resolved_this_week': mine.filter(
                status__in=FINISHED, resolved_at__gte=week_ago
            ).count(),
            'unassigned_pool': pool.count(),
            'total_handled': sum(status_counts.values()),
        },
        'status_chart': _chart(status_counts, Complaint.Status.choices),
        'my_queue': (
            mine.unresolved()
            .select_related(*RELATED)
            .annotate(rank=_priority_rank())
            .order_by('rank', 'created_at')[:10]
        ),
        'unassigned_queue': (
            pool.select_related(*RELATED)
            .annotate(rank=_priority_rank())
            .order_by('rank', 'created_at')[:5]
        ),
    }

@role_required(*ADMIN_ONLY)
def admin_dashboard(request):
    return render(request, 'dashboard/admin_dashboard.html', get_admin_dashboard_data())


@role_required(*STAFF_ONLY)
def staff_dashboard(request):
    return render(request, 'dashboard/staff_dashboard.html', get_staff_dashboard_data(request.user))


def _csv_safe(value):
  
    text = '' if value is None else str(value)
    return f"'{text}" if text[:1] in ('=', '+', '-', '@', '\t', '\r') else text


@role_required(*ADMIN_ONLY)
def export_complaints_csv(request):
   
    queryset = Complaint.objects.select_related(*RELATED)
    status = request.GET.get('status')
    if status in Complaint.Status.values:
        queryset = queryset.filter(status=status)

    response = HttpResponse(content_type='text/csv')
    filename = f'complaints_{timezone.localdate():%Y%m%d}.csv'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    def fmt(dt):
        return timezone.localtime(dt).strftime('%Y-%m-%d %H:%M') if dt else ''

    writer = csv.writer(response)
    writer.writerow([
        'Ticket ID', 'Title', 'Category', 'Priority', 'Status', 'Complainant',
        'Complainant email', 'Assigned to', 'Created', 'Resolved',
    ])
    for c in queryset.iterator():
        writer.writerow([_csv_safe(v) for v in (
            c.ticket_id, c.title, c.category.name, c.get_priority_display(),
            c.get_status_display(), c.complainant.display_name, c.complainant.email,
            c.assigned_to.display_name if c.assigned_to else '',
            fmt(c.created_at), fmt(c.resolved_at),
        )])
    return response