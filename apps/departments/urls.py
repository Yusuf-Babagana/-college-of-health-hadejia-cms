from django.urls import path

from . import views

app_name = 'departments'

urlpatterns = [
    path('', views.DepartmentListView.as_view(), name='department_list'),
    path('create/', views.DepartmentCreateView.as_view(), name='department_create'),
    path('<uuid:pk>/edit/', views.DepartmentUpdateView.as_view(), name='department_update'),
    path('<uuid:pk>/archive-toggle/', views.DepartmentArchiveToggleView.as_view(), name='department_archive_toggle'),
    path('<uuid:pk>/assign-hod/', views.AssignHODView.as_view(), name='assign_hod'),
]
