from django.urls import path

from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.AccountLoginView.as_view(), name='login'),
    path('logout/', views.AccountLogoutView.as_view(), name='logout'),
    path('password-reset/', views.AccountPasswordResetView.as_view(), name='password_reset'),
    path('password-reset/done/', views.AccountPasswordResetDoneView.as_view(), name='password_reset_done'),
    path(
        'reset/<uidb64>/<token>/',
        views.AccountPasswordResetConfirmView.as_view(),
        name='password_reset_confirm',
    ),
    path('reset/complete/', views.AccountPasswordResetCompleteView.as_view(), name='password_reset_complete'),
    path('password-change/', views.ChangePasswordView.as_view(), name='password_change'),
    path('profile/', views.ProfileView.as_view(), name='profile'),

    path('users/', views.UserListView.as_view(), name='user_list'),
    path('users/create/', views.UserCreateView.as_view(), name='user_create'),
    path('users/<uuid:pk>/edit/', views.UserUpdateView.as_view(), name='user_update'),
    path('users/<uuid:pk>/toggle-active/', views.UserToggleActiveView.as_view(), name='user_toggle_active'),
]
