from django.urls import path

from . import views

app_name = 'courses'

urlpatterns = [
    path('', views.CourseListView.as_view(), name='course_list'),
    path('create/', views.CourseCreateView.as_view(), name='course_create'),
    path('<uuid:pk>/edit/', views.CourseUpdateView.as_view(), name='course_update'),
    path('<uuid:pk>/archive-toggle/', views.CourseArchiveToggleView.as_view(), name='course_archive_toggle'),

    path('allocate/', views.CourseAllocationView.as_view(), name='course_allocation'),
    path('offerings/', views.CourseOfferingListView.as_view(), name='course_offering_list'),
    path('offerings/create/', views.CourseOfferingCreateView.as_view(), name='course_offering_create'),
    path('offerings/<uuid:pk>/edit/', views.CourseOfferingUpdateView.as_view(), name='course_offering_update'),
    path(
        'offerings/<uuid:pk>/archive-toggle/',
        views.CourseOfferingArchiveToggleView.as_view(),
        name='course_offering_archive_toggle',
    ),

    path('registrations/', views.DepartmentRegistrationListView.as_view(), name='department_registrations'),
    path('registrations/<uuid:pk>/cancel/', views.HODCancelRegistrationView.as_view(), name='cancel_registration'),

    path('available/', views.AvailableCourseListView.as_view(), name='available_courses'),
    path('available/<uuid:pk>/register/', views.RegisterCourseView.as_view(), name='register_course'),
    path('my-registrations/', views.MyCourseRegistrationsView.as_view(), name='my_registrations'),
    path('my-registrations/<uuid:pk>/drop/', views.DropCourseView.as_view(), name='drop_course'),
    path('my-registrations/slip/', views.RegistrationSlipPDFView.as_view(), name='registration_slip'),
]
