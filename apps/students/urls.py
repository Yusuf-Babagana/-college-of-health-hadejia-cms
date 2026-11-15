from django.urls import path

from . import views

app_name = 'students'

urlpatterns = [
    path('', views.StudentListView.as_view(), name='student_list'),
    path('add/', views.StudentCreateView.as_view(), name='student_create'),
    path('promote/', views.StudentBulkPromoteView.as_view(), name='bulk_promote'),
    path('<uuid:pk>/edit/', views.StudentProfileUpdateView.as_view(), name='student_update'),
    path('<uuid:pk>/status/', views.StudentStatusUpdateView.as_view(), name='student_status_update'),
    path('<uuid:pk>/promote/', views.StudentPromoteView.as_view(), name='student_promote'),
    path('<uuid:pk>/archive-toggle/', views.StudentArchiveToggleView.as_view(), name='student_archive_toggle'),

    path('department/', views.DepartmentStudentListView.as_view(), name='department_student_list'),
]
