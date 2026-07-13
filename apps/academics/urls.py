from django.urls import path

from . import views

app_name = 'academics'

urlpatterns = [
    path('sessions/', views.SessionListView.as_view(), name='session_list'),
    path('sessions/create/', views.SessionCreateView.as_view(), name='session_create'),
    path('sessions/<uuid:pk>/edit/', views.SessionUpdateView.as_view(), name='session_update'),
    path('sessions/<uuid:pk>/archive-toggle/', views.SessionArchiveToggleView.as_view(), name='session_archive_toggle'),

    path('semesters/', views.SemesterListView.as_view(), name='semester_list'),
    path('semesters/create/', views.SemesterCreateView.as_view(), name='semester_create'),
    path('semesters/<uuid:pk>/edit/', views.SemesterUpdateView.as_view(), name='semester_update'),
    path('semesters/<uuid:pk>/archive-toggle/', views.SemesterArchiveToggleView.as_view(), name='semester_archive_toggle'),
    path('semesters/<uuid:pk>/registration-window/', views.SemesterRegistrationWindowView.as_view(), name='registration_window'),

    path('level-states/', views.LevelSemesterStateView.as_view(), name='level_states'),
]
