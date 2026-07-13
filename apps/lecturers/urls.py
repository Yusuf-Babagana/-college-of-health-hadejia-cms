from django.urls import path

from . import views

app_name = 'lecturers'

urlpatterns = [
    path('', views.LecturerListView.as_view(), name='lecturer_list'),
    path('create/', views.LecturerCreateView.as_view(), name='lecturer_create'),
    path('<uuid:pk>/edit/', views.LecturerUpdateView.as_view(), name='lecturer_update'),
    path('<uuid:pk>/archive-toggle/', views.LecturerArchiveToggleView.as_view(), name='lecturer_archive_toggle'),
]
