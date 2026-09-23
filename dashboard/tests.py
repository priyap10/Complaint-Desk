import csv
import io

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from complaints.models import Category, Complaint

from .views import TREND_DAYS, get_admin_dashboard_data, get_staff_dashboard_data

PASSWORD = 'StrongPass#2024'


class DashboardTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user('admin1', 'admin1@example.com', PASSWORD, role=User.Role.ADMIN)
        cls.staff = User.objects.create_user('staff1', 'staff1@example.com', PASSWORD, role=User.Role.STAFF)
        cls.user = User.objects.create_user('user1', 'user1@example.com', PASSWORD)
        cls.category = Category.objects.create(name='Delivery')

    def make(self, **kwargs):
        data = {
            'title': 'Late delivery',
            'description': 'Arrived late.',
            'category': self.category,
            'complainant': self.user,
        }
        data.update(kwargs)
        return Complaint.objects.create(**data)


class DataBuilderTests(DashboardTestCase):
    def setUp(self):
        self.make()                                                        # open, unassigned
        self.make(priority=Complaint.Priority.URGENT)                      # open, unassigned, urgent
        self.make(status=Complaint.Status.IN_PROGRESS, assigned_to=self.staff)
        self.make(status=Complaint.Status.RESOLVED, assigned_to=self.staff)

    def test_admin_counts(self):
        stats = get_admin_dashboard_data()['stats']
        self.assertEqual(stats['total'], 4)
        self.assertEqual(stats['open'], 2)
        self.assertEqual(stats['in_progress'], 1)
        self.assertEqual(stats['resolved'], 1)
        self.assertEqual(stats['unassigned'], 2)
        self.assertEqual(stats['urgent_open'], 1)
        self.assertIsNotNone(stats['avg_resolution_days'])

    def test_charts_have_matching_labels_and_values(self):
        data = get_admin_dashboard_data()
        for key in ('status_chart', 'priority_chart'):
            self.assertEqual(len(data[key]['labels']), len(data[key]['values']))
        self.assertEqual(sum(data['status_chart']['values']), 4)
        self.assertEqual(data['category_chart'], {'labels': ['Delivery'], 'values': [4]})

    def test_trend_covers_every_day(self):
        trend = get_admin_dashboard_data()['trend_chart']
        self.assertEqual(len(trend['labels']), TREND_DAYS)
        self.assertEqual(sum(trend['created']), 4)   # all created today
        self.assertEqual(sum(trend['resolved']), 1)

    def test_urgent_unassigned_needs_attention(self):
        attention = list(get_admin_dashboard_data()['needs_attention'])
        self.assertEqual(len(attention), 1)
        self.assertEqual(attention[0].priority, Complaint.Priority.URGENT)

    def test_staff_workload(self):
        workload = list(get_admin_dashboard_data()['staff_workload'])
        self.assertEqual(workload[0], self.staff)
        self.assertEqual(workload[0].active_count, 1)
        self.assertEqual(workload[0].finished_count, 1)

    def test_staff_dashboard_data(self):
        data = get_staff_dashboard_data(self.staff)
        self.assertEqual(data['stats']['active'], 1)
        self.assertEqual(data['stats']['resolved_this_week'], 1)
        self.assertEqual(data['stats']['unassigned_pool'], 2)
        self.assertEqual(len(data['my_queue']), 1)
        self.assertEqual(data['unassigned_queue'][0].priority, Complaint.Priority.URGENT)  # urgent first


class HomeRedirectTests(DashboardTestCase):
    def test_each_role_lands_on_its_own_page(self):
        cases = [
            (self.admin, 'dashboard:admin_dashboard'),
            (self.staff, 'dashboard:staff_dashboard'),
            (self.user, 'complaints:my_list'),
        ]
        for user, target in cases:
            self.client.force_login(user)
            response = self.client.get(reverse('accounts:home'))
            self.assertRedirects(response, reverse(target), fetch_redirect_response=False)


class CsvExportTests(DashboardTestCase):
    def test_admin_can_download_csv(self):
        self.make(title='=HYPERLINK("http://evil.example")')
        self.make(status=Complaint.Status.RESOLVED)
        self.client.force_login(self.admin)

        response = self.client.get(reverse('dashboard:export_csv'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')

        rows = list(csv.reader(io.StringIO(response.content.decode())))
        self.assertEqual(rows[0][0], 'Ticket ID')
        self.assertEqual(len(rows), 3)                       # header + 2 complaints
        titles = [row[1] for row in rows[1:]]
        self.assertIn('\'=HYPERLINK("http://evil.example")', titles)  

    def test_status_filter(self):
        self.make()
        self.make(status=Complaint.Status.RESOLVED)
        self.client.force_login(self.admin)
        response = self.client.get(reverse('dashboard:export_csv'), {'status': 'resolved'})
        rows = list(csv.reader(io.StringIO(response.content.decode())))
        self.assertEqual(len(rows), 2)