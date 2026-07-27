from django.urls import path

from . import views

app_name = 'admissions'

urlpatterns = [
    path('', views.HomeView.as_view(), name='home'),
    path('signup/', views.SignupView.as_view(), name='signup'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('referral/', views.ReferralCodeView.as_view(), name='referral_check'),
    path('pay/', views.InitiateAdmissionPaymentView.as_view(), name='initiate_payment'),
    path('pay/callback/', views.AdmissionPaymentCallbackView.as_view(), name='payment_callback'),
    path('pay/webhook/', views.AdmissionPaystackWebhookView.as_view(), name='payment_webhook'),
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),
    path('apply/personal/', views.SectionAView.as_view(), name='section_a'),
    path('apply/education/', views.SectionBView.as_view(), name='section_b'),
    path('apply/results/', views.SectionCView.as_view(), name='section_c'),
    path('apply/courses/', views.SectionDView.as_view(), name='section_d'),
    path('apply/declaration/', views.SectionEView.as_view(), name='section_e'),
    path('apply/summary/', views.SummaryView.as_view(), name='summary'),
    path('apply/download/', views.ApplicationPDFView.as_view(), name='application_pdf'),
]
