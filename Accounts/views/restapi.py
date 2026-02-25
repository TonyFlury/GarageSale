import json
from http import HTTPStatus

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import BadRequest
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from Accounts.models import UploadHistory, Transaction, Categories, UploadError

### REST API starts here - would be nicer to do some sort of class with a dynamic dispatch based on verb
# Also URLs need tweaking to make it clear that these are rest APIs
# Also need to change the common.js file to the new URLs
# Does Django REST API work for this, or do I need to roll my own - which isn't complex

def _build_tx_record(account, history_inst: UploadHistory, tx_number: int, row) -> tuple[
    Any, tuple[Transaction, bool], str | Any, str | Any]:
    """Build a transaction record from the data in the row"""

    debit, credit = row['Debit Amount'], row['Credit Amount']
    debit = debit if debit else "0"
    credit = credit if credit else "0"
    category = row.get('Category', '')

    data_dict = {'transaction_date': datetime.strptime(row['Transaction Date'], '%d/%m/%Y'),
                 'description': row['Transaction Description'],
                 'tx_number': tx_number,
                 'upload_history': history_inst,
                 'debit': Decimal(debit), 'credit': Decimal(credit),
                 'balance': Decimal(row['Balance']),
                 'category': category}

    instance = Transaction.objects.get_or_create(account=account, **data_dict)
    return category, credit, debit, instance

@require_http_methods(['GET'])
def get_child_categories(request, transaction_id):
    try:
        transaction = Transaction.objects.get(id=transaction_id)
    except Transaction.DoesNotExist:
        logging.error(f'Transaction {transaction_id} not found')
        raise BadRequest(f'Transaction {transaction_id} not found')

    parent_category = transaction.category
    cat_list = list(i for i in Categories.objects.filter(parent__category_name=parent_category).
                                           values_list('category_name', flat=True))
    print(cat_list)
    return JsonResponse({'categories':cat_list, 'success':HTTPStatus.OK})

@require_http_methods(['GET'])
def get_categories(request, transaction_id):
    """Return the valid categories for the specified transaction"""
    try:
        transaction = Transaction.objects.get(id=transaction_id)
    except Transaction.DoesNotExist:
        logging.error(f'Transaction {transaction_id} not found')
        raise BadRequest(f'Transaction {transaction_id} not found')

    if transaction.parent is None:
        tx_type = 'C' if transaction.credit > 0 else 'D'
        cat_list = list(Categories.objects.filter(credit_debit=tx_type, parent__isnull=True).values_list('category_name', flat=True))
    else:
        parent_category = transaction.parent.category
        cat_list = list(i for i in Categories.objects.filter(parent__category_name=parent_category).
                                               values_list('category_name', flat=True))

    return JsonResponse({'categories':cat_list, 'success':HTTPStatus.OK})


def edit_transaction(request, transaction_id):
    try:
        transaction = Transaction.objects.get(id=transaction_id)
    except Transaction.DoesNotExist:
        logging.error(f'Transaction {transaction_id} not found')
        raise BadRequest(f'Transaction {transaction_id} not found')

    data = json.loads(request.body)

    if 'name' in data:
        transaction.name = data['name']
    if category := data.get('category'):
        transaction.category = category
    transaction.save()
    errors = UploadError.objects.get(transaction=transaction)
    if errors:
        errors.delete()

    return JsonResponse({'message':"edit_transaction : transaction updated successfully",'success':HTTPStatus.OK})


@require_http_methods(['PUT'])
@user_passes_test(lambda u: u.is_superuser or u.has_perm('Accounts.change_transaction'))
def edit_split(request, transaction_id):
    try:
        transaction = Transaction.objects.get(id=transaction_id)
    except Transaction.DoesNotExist:
        logging.error(f'Transaction {transaction_id} not found')
        raise BadRequest(f'Transaction {transaction_id} not found')

    data = json.loads(request.body)

    amount_type = 'debit' if 'debit' in data else 'credit'

    transaction.category = data['category']
    setattr(transaction, amount_type, Decimal(data[amount_type]))
    transaction.save()
    return JsonResponse({'message':"edit_transaction : transaction updated successfully",'success':HTTPStatus.OK})


@require_http_methods(['PUT'])
@user_passes_test(lambda u: u.is_superuser or u.has_perm('Accounts.change_transaction'))
def add_split(request, transaction_id):
    try:
        transaction = Transaction.objects.get(id=transaction_id)
    except Transaction.DoesNotExist:
       logging.error(f'Transaction {transaction_id} not found')
       raise BadRequest(f'Transaction {transaction_id} not found')

    data = json.loads(request.body)

    amount_type = 'debit' if 'debit' in data else 'credit'

    new_id = Transaction.objects.create(account=transaction.account, parent=transaction, transaction_date=transaction.transaction_date,
                                            category=data['category'],
                                             **{amount_type:Decimal(data[amount_type])})
    logging.info(f"add_transaction : {new_id}")

    return JsonResponse({'message':"add_transaction : transaction updated successfully",'id':new_id.id, 'success':HTTPStatus.OK})


@require_http_methods(['PUT'])
@user_passes_test(lambda u: u.is_superuser or u.has_perm('Accounts.change_transaction'))
def delete_transaction(request, transaction_id):
    try:
        transaction = Transaction.objects.get(id=transaction_id)
    except Transaction.DoesNotExist:
       logging.error(f'Transaction {transaction_id} not found')
       raise BadRequest(f'Transaction {transaction_id} not found')

    transaction.delete()
    logging.info(f"delete transaction: {transaction_id} deleted")

    return JsonResponse({'message':"delete_transaction : transaction delete successfully",'success':HTTPStatus.OK})
