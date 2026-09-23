from django.urls import path

from . import views

app_name = 'complaints'

urlpatterns = [
    path('', views.complaint_list, name='list'),                       # staff / admin
    path('mine/', views.my_complaints, name='my_list'),                # complainant
    path('new/', views.complaint_create, name='create'),
    path('<int:pk>/', views.complaint_detail, name='detail'),
    path('<int:pk>/edit/', views.complaint_edit, name='edit'),
    path('<int:pk>/delete/', views.complaint_delete, name='delete'),
    path('<int:pk>/comment/', views.add_comment, name='comment'),      # POST
    path('<int:pk>/manage/', views.manage_complaint, name='manage'),   # POST
    path('<int:pk>/claim/', views.claim_complaint, name='claim'),      # POST
    path('attachments/<int:pk>/delete/', views.attachment_delete, name='attachment_delete'),  # POST
]