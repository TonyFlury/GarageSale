from django.urls import path, include

from .views import views as views
from .views import restapi as Rest_API

app_name = "Account"

urlpatterns = [
    path('upload/', views.upload_transactions, name='upload_transactions'),
    path('uploadErrors/', views.UploadErrorList.as_view(), name='UploadErrorList'),
    path('uploadErrors/<int:account_id>/', views.UploadErrorList.as_view(), name='UploadErrorList'),
    path('uploadErrors/<int:account_id>/<int:upload_id>/', views.UploadErrorList.as_view(), name='UploadErrorList'),

    path('report/transactions/', views.TransactionList.as_view(), name='TransactionList'),
    path('report/transactions/<int:account_id>/', views.TransactionList.as_view(), name='TransactionList'),

    path('report/', views.FinancialReport.as_view(), name='report'),
    path('report/<int:account_id>/', views.FinancialReport.as_view(), name='report'),

    #ToDo - a single REST API with actions - maybe ?
    path('get_category_list/<int:transaction_id>/', Rest_API.get_categories, name='get_categories'),
    path('get_child_categories/<int:transaction_id>/', Rest_API.get_child_categories, name='get_child_categories'),
    path('edit_transaction/<int:transaction_id>/', Rest_API.edit_transaction, name='edit_transaction'),
    path('edit_split/<int:transaction_id>/', Rest_API.edit_split, name='edit_split'),
    path('add_split/<int:transaction_id>/', Rest_API.add_split, name='edit_split'),
    path( 'delete_transaction/<int:transaction_id>/', Rest_API.delete_transaction, name='delete_transaction')
]