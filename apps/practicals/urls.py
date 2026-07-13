from django.urls import path

from . import views

app_name = 'practicals'

urlpatterns = [
    path('', views.PracticalPlacementListView.as_view(), name='placement_list'),
    path('<uuid:pk>/edit/', views.PracticalPlacementUpdateView.as_view(), name='placement_update'),
    path('export/', views.PracticalPlacementExportView.as_view(), name='placement_export'),
]
