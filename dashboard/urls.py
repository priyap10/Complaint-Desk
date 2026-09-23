from django.urls import path

from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.admin_dashboard, name='admin_dashboard'),
    path('staff/', views.staff_dashboard, name='staff_dashboard'),
    path('export/complaints.csv', views.export_complaints_csv, name='export_csv'),
]