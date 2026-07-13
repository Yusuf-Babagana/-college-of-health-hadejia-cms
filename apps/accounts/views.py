from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import FormView, ListView, UpdateView, View

from apps.core.constants import Role
from apps.core.mixins import PaginatedListMixin, RoleRequiredMixin

from . import selectors, services
from .forms import (
    AdminUserCreateForm,
    AdminUserUpdateForm,
    ProfileUpdateForm,
    StyledAuthenticationForm,
    StyledPasswordChangeForm,
    StyledPasswordResetForm,
    StyledSetPasswordForm,
)
from .models import User


class AccountLoginView(LoginView):
    template_name = 'accounts/login.html'
    authentication_form = StyledAuthenticationForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        messages.success(self.request, f'Welcome back, {form.get_user().get_full_name() or form.get_user().username}!')
        return super().form_valid(form)


class AccountLogoutView(LogoutView):
    next_page = 'accounts:login'

    def dispatch(self, request, *args, **kwargs):
        messages.info(request, 'You have been signed out.')
        return super().dispatch(request, *args, **kwargs)


class AccountPasswordResetView(PasswordResetView):
    template_name = 'accounts/password_reset.html'
    email_template_name = 'accounts/password_reset_email.html'
    subject_template_name = 'accounts/password_reset_subject.txt'
    form_class = StyledPasswordResetForm
    success_url = reverse_lazy('accounts:password_reset_done')


class AccountPasswordResetDoneView(PasswordResetDoneView):
    template_name = 'accounts/password_reset_done.html'


class AccountPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = 'accounts/password_reset_confirm.html'
    form_class = StyledSetPasswordForm
    success_url = reverse_lazy('accounts:password_reset_complete')


class AccountPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = 'accounts/password_reset_complete.html'


class ProfileView(LoginRequiredMixin, UpdateView):
    template_name = 'accounts/profile.html'
    form_class = ProfileUpdateForm
    success_url = reverse_lazy('accounts:profile')

    def get_object(self, queryset=None):
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, 'Your profile has been updated.')
        return super().form_valid(form)


class ChangePasswordView(LoginRequiredMixin, View):
    """Dedicated change-password view kept separate from ProfileView so a
    failed password attempt never risks clobbering profile fields.
    """
    template_name = 'accounts/change_password.html'

    def get(self, request):
        form = StyledPasswordChangeForm(user=request.user)
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = StyledPasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            services.complete_password_change(request, form)
            messages.success(request, 'Your password has been changed successfully.')
            return redirect('accounts:profile')
        return render(request, self.template_name, {'form': form})


class UserManagementRoleMixin(RoleRequiredMixin):
    allowed_roles = (Role.ICT_ADMIN, Role.SUPER_ADMIN)


class UserListView(UserManagementRoleMixin, PaginatedListMixin, ListView):
    template_name = 'accounts/user_list.html'
    context_object_name = 'users'

    def get_queryset(self):
        return selectors.get_user_list(
            search=self.request.GET.get('q'),
            role=self.request.GET.get('role'),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['role_choices'] = Role.choices
        context['current_role'] = self.request.GET.get('role', '')
        context['search_query'] = self.request.GET.get('q', '')
        return context


class UserCreateView(UserManagementRoleMixin, FormView):
    form_class = AdminUserCreateForm
    template_name = 'accounts/user_form.html'
    success_url = reverse_lazy('accounts:user_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = 'Create User'
        return context

    def form_valid(self, form):
        data = form.cleaned_data
        user, generated_password = services.create_user(
            username=data['username'],
            email=data['email'],
            first_name=data['first_name'],
            last_name=data['last_name'],
            role=data['role'],
            phone_number=data['phone_number'],
            password=data.get('password1') or None,
        )
        if generated_password:
            password_note = (
                f'Temporary password: {generated_password} '
                '(shown once - share it securely; they must change it on first login).'
            )
        else:
            password_note = 'They must change the password you set on first login.'

        messages.success(
            self.request,
            f'User "{user.username}" created with role "{user.get_role_display()}". {password_note}',
        )
        return redirect(self.success_url)


class UserUpdateView(UserManagementRoleMixin, UpdateView):
    model = User
    form_class = AdminUserUpdateForm
    template_name = 'accounts/user_form.html'
    success_url = reverse_lazy('accounts:user_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = f'Edit {self.object.username}'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'User "{self.object.username}" updated.')
        return super().form_valid(form)


class UserToggleActiveView(UserManagementRoleMixin, View):
    def post(self, request, pk):
        user = User.objects.get(pk=pk)
        try:
            if user.is_active_account:
                services.deactivate_user(user, acting_user=request.user)
                messages.success(request, f'User "{user.username}" has been deactivated.')
            else:
                services.reactivate_user(user)
                messages.success(request, f'User "{user.username}" has been reactivated.')
        except ValidationError as exc:
            messages.error(request, exc.message)
        return redirect('accounts:user_list')
