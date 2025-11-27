from django.urls import path, include

from . import views

app_name = "Account"

urlpatterns = [
    path('upload/', views.upload_transactions, name='upload_transactions'),
    path('report/<int:account_id>/transactions/', views.TransactionList.as_view(), name='TransactionList'),

    path('report/', views.summary, name='report'),
    path('report/<int:account_id>/', views.summary, name='report'),
    path('report/', include([
            path('<str:report>/', include([
                path('', views.download_report, name='download_report'),
                path('<int:account>/', include([
                    path('', views.download_report, name='download_report'),
                    path('<int:year>/', include([
                        path('', views.download_report, name='download_report'),
                        path('<str:month>/', views.download_report, name='Summary'),
                    ])
                         )
                ])
                     )
            ])
                 )
         ])
         ),
    path('edit_transaction/<int:transaction_id>/', views.edit_transaction, name='edit_transaction')
]