from django.contrib import admin

from apps.core.admin import SoftDeleteAdminMixin

from .models import FeeStructure, FeeType, Invoice, Payment


@admin.register(FeeType)
class FeeTypeAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'description', 'is_deleted')
    search_fields = ('name',)
    ordering = ('name',)
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(FeeStructure)
class FeeStructureAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ('fee_type', 'department', 'level', 'session', 'amount', 'is_deleted')
    list_filter = SoftDeleteAdminMixin.list_filter + ('fee_type', 'session', 'department', 'level')
    search_fields = ('department__name', 'department__code', 'session__name', 'fee_type__name')
    autocomplete_fields = ('department', 'session', 'fee_type')
    ordering = ('-session__name', 'department__code', 'level')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(Invoice)
class InvoiceAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ('student', 'fee_structure', 'amount_due', 'amount_paid', 'status', 'due_date', 'is_deleted')
    list_filter = SoftDeleteAdminMixin.list_filter + ('status', 'fee_structure__session', 'fee_structure__department')
    search_fields = ('student__matric_number', 'student__user__first_name', 'student__user__last_name')
    autocomplete_fields = ('student', 'fee_structure')
    ordering = ('-issued_date',)
    readonly_fields = ('id', 'issued_date', 'created_at', 'updated_at')


@admin.register(Payment)
class PaymentAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ('reference', 'invoice', 'amount', 'method', 'status', 'paid_at', 'verified_by', 'is_deleted')
    list_filter = SoftDeleteAdminMixin.list_filter + ('method', 'status')
    search_fields = ('reference', 'invoice__student__matric_number')
    autocomplete_fields = ('invoice', 'verified_by')
    ordering = ('-created_at',)
    readonly_fields = ('id', 'created_at', 'updated_at')
