from django.urls import path

from . import views

app_name = 'finance'

urlpatterns = [
    path('fee-types/', views.FeeTypeListView.as_view(), name='fee_type_list'),
    path('fee-types/create/', views.FeeTypeCreateView.as_view(), name='fee_type_create'),
    path('fee-types/<uuid:pk>/edit/', views.FeeTypeUpdateView.as_view(), name='fee_type_update'),
    path(
        'fee-types/<uuid:pk>/archive-toggle/',
        views.FeeTypeArchiveToggleView.as_view(),
        name='fee_type_archive_toggle',
    ),

    path('fee-structures/', views.FeeStructureListView.as_view(), name='fee_structure_list'),
    path('fee-structures/create/', views.FeeStructureCreateView.as_view(), name='fee_structure_create'),
    path('fee-structures/<uuid:pk>/edit/', views.FeeStructureUpdateView.as_view(), name='fee_structure_update'),
    path(
        'fee-structures/<uuid:pk>/archive-toggle/',
        views.FeeStructureArchiveToggleView.as_view(),
        name='fee_structure_archive_toggle',
    ),

    path('invoices/', views.InvoiceListView.as_view(), name='invoice_list'),
    path('invoices/generate/bulk/', views.BulkInvoiceGenerateView.as_view(), name='invoice_generate_bulk'),
    path(
        'invoices/generate/bulk-all-fee-types/',
        views.BulkInvoiceGenerateAllFeeTypesView.as_view(),
        name='invoice_generate_bulk_all_fee_types',
    ),
    path('invoices/generate/individual/', views.IndividualInvoiceGenerateView.as_view(), name='invoice_generate_individual'),

    path('my-invoices/', views.MyInvoicesView.as_view(), name='my_invoices'),
    path('my-invoices/<uuid:pk>/pay/', views.InitiateOnlinePaymentView.as_view(), name='initiate_payment'),
    path('payments/callback/', views.PaymentCallbackView.as_view(), name='payment_callback'),
    path('payments/webhook/', views.PaystackWebhookView.as_view(), name='payment_webhook'),

    path('payments/', views.PaymentListView.as_view(), name='payment_list'),
    path('payments/record-offline/', views.RecordOfflinePaymentView.as_view(), name='record_offline_payment'),
    path('payments/<uuid:pk>/verify/', views.VerifyOnlinePaymentView.as_view(), name='verify_online_payment'),

    path('defaulters/', views.DefaulterListView.as_view(), name='defaulter_list'),
    path('defaulters/export/', views.DefaulterExportView.as_view(), name='defaulter_export'),
]
