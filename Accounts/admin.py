from django.contrib import admin
from django.contrib.admin import HORIZONTAL
from django.db import models

from .models import Transaction, Account, Categories, FinancialYear, UploadError, UploadHistory


# Register your models here.
@admin.register(UploadHistory)
class UploadHistoryAdmin(admin.ModelAdmin):
    list_display = ['uploaded_by', 'uploaded_at', 'start_date', 'end_date', 'account']
    date_hierarchy = 'uploaded_at'

@admin.register(UploadError)
class UploadErrorAdmin(admin.ModelAdmin):
    list_display = ['upload_history', 'transaction', 'error_message']
    date_hierarchy = 'upload_history__uploaded_at'

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['transaction_date',  'description','credit', 'debit']
    date_hierarchy = 'transaction_date'

@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    pass


class CategoryProxy(Categories):
    class Meta:
        proxy = True

class CategoryInline(admin.TabularInline):
      list_display = ("category_name", "credit_debit", "parent")
      radio_fields = {'credit_debit': HORIZONTAL}
      extra = 0
      model = CategoryProxy

@admin.register(Categories)
class CategoriesAdmin(admin.ModelAdmin):
    list_display = ['category_name', 'credit_debit']
    radio_fields = {'credit_debit': HORIZONTAL}
    inlines = [CategoryInline]
    def get_queryset(self, request):
        """Now maybe you want to only show the "root" categories, the ones that have no parent, then you can override the `queryset` attribute or the `get_queryset` method"""
        return super().get_queryset(request).filter(parent__isnull=True)

@admin.register(FinancialYear)
class FinancialYearAdmin(admin.ModelAdmin):
    pass