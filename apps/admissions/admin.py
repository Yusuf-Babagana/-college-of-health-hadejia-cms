import csv

from django.contrib import admin
from django.http import HttpResponse
from django.utils import timezone

from apps.core.admin import SoftDeleteAdminMixin

from .models import (
    AdmissionPayment,
    Applicant,
    Application,
    Programme,
    ReferralCode,
    SchoolAttended,
    SSCESitting,
    SSCESubjectResult,
    UploadedDocument,
)


@admin.register(Programme)
class ProgrammeAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'short_code', 'is_active')
    list_editable = ('is_active',)
    search_fields = ('name', 'short_code')


@admin.register(ReferralCode)
class ReferralCodeAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ('code', 'batch_label', 'used_by', 'used_at')
    list_filter = SoftDeleteAdminMixin.list_filter + ('batch_label',)
    search_fields = ('code', 'batch_label')
    readonly_fields = ('used_by', 'used_at')
    autocomplete_fields = ('used_by',)


@admin.register(Applicant)
class ApplicantAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ('user', 'has_paid', 'payment_verified_at', 'referral_code_used')
    list_filter = SoftDeleteAdminMixin.list_filter + ('has_paid',)
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'user__username')
    autocomplete_fields = ('user', 'referral_code_used')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(AdmissionPayment)
class AdmissionPaymentAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ('reference', 'applicant', 'amount', 'status', 'paid_at')
    list_filter = SoftDeleteAdminMixin.list_filter + ('status',)
    search_fields = ('reference', 'applicant__user__email')
    autocomplete_fields = ('applicant',)
    readonly_fields = ('id', 'reference', 'amount', 'status', 'paid_at', 'raw_response', 'created_at', 'updated_at')


class SchoolAttendedInline(admin.TabularInline):
    model = SchoolAttended
    extra = 0


class SSCESittingInline(admin.TabularInline):
    model = SSCESitting
    extra = 0


class UploadedDocumentInline(admin.TabularInline):
    model = UploadedDocument
    extra = 0


@admin.register(Application)
class ApplicationAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = (
        'applicant', 'programme_first_choice', 'status', 'completion_percent', 'submitted_at',
    )
    list_filter = SoftDeleteAdminMixin.list_filter + ('status', 'programme_first_choice')
    search_fields = (
        'applicant__user__email', 'applicant__user__first_name', 'applicant__user__last_name',
    )
    autocomplete_fields = ('applicant', 'programme_first_choice', 'programme_second_choice', 'reviewed_by')
    readonly_fields = (
        'id', 'created_at', 'updated_at', 'submitted_at',
        'section_a_complete', 'section_b_complete', 'section_c_complete',
        'section_d_complete', 'section_e_complete',
    )
    inlines = [SchoolAttendedInline, SSCESittingInline, UploadedDocumentInline]
    actions = ('approve_selected', 'reject_selected', 'export_as_csv')

    @admin.action(description='Approve selected applications')
    def approve_selected(self, request, queryset):
        queryset.update(status=Application.Status.APPROVED, reviewed_by=request.user, reviewed_at=timezone.now())

    @admin.action(description='Reject selected applications')
    def reject_selected(self, request, queryset):
        queryset.update(status=Application.Status.REJECTED, reviewed_by=request.user, reviewed_at=timezone.now())

    @admin.action(description='Export selected to CSV')
    def export_as_csv(self, request, queryset):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="applications.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'Applicant Email', 'Applicant Name', 'Programme (1st choice)', 'Programme (2nd choice)',
            'Status', 'Submitted At',
        ])
        for application in queryset.select_related(
            'applicant__user', 'programme_first_choice', 'programme_second_choice',
        ):
            user = application.applicant.user
            writer.writerow([
                user.email,
                user.get_full_name(),
                application.programme_first_choice,
                application.programme_second_choice,
                application.get_status_display(),
                application.submitted_at,
            ])
        return response


@admin.register(SSCESubjectResult)
class SSCESubjectResultAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ('sitting', 'subject_name', 'grade')
    search_fields = ('subject_name',)
