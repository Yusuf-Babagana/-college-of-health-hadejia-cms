from django.urls import path

from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.HomeView.as_view(), name='home'),
    path('dashboard/', views.DashboardRedirectView.as_view(), name='redirect'),
    path('student/', views.StudentDashboardView.as_view(), name='student'),
    path('lecturer/', views.LecturerDashboardView.as_view(), name='lecturer'),
    path('hod/', views.HODDashboardView.as_view(), name='hod'),
    path('registrar/', views.RegistrarDashboardView.as_view(), name='registrar'),
    path('bursar/', views.BursarDashboardView.as_view(), name='bursar'),
    path('exam-officer/', views.ExamOfficerDashboardView.as_view(), name='exam_officer'),
    path('practical-coordinator/', views.PracticalCoordinatorDashboardView.as_view(), name='practical_coordinator'),
    path('ict-admin/', views.ICTAdminDashboardView.as_view(), name='ict_admin'),
    path('super-admin/', views.SuperAdminDashboardView.as_view(), name='super_admin'),
]
