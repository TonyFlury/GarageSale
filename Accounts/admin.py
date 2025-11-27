from django.contrib import admin

from .models import Transaction, Account, Categories

# Register your models here.
@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['transaction_date',  'description', 'debit','credit']
    date_hierarchy = 'transaction_date'

@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    pass

@admin.register(Categories)
class CategoriesAdmin(admin.ModelAdmin):
    pass