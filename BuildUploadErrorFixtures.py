#! /usr/bin/env python3
import datetime
from datetime import timedelta as td
import json
from decimal import Decimal

import click
import random
from itertools import count

from django.template.defaultfilters import default

class GenerateFixture:
    def __init__(self, context):
        self._context = context.obj
        self._uploads = []
        self._transactions = []
        self._errors = []
        self._account = json.load(open(self._context['account_file']))
        self._user = json.load(open(self._context['user_file']))
        self._category = json.load(open(self._context['category_file']))

    def verbose(self,msg):
        if self._context['verbosity']:
            click.echo(msg)

    def _account_nk(self, account):
        return [ account['fields']['bank_name'], account['fields']['sort_code'], account['fields']['account_number']]
    def _user_nk(self, user):
        return [user['fields']['email']]
    def _category_nk(self, category):
        return [category['fields']['category_name']]
    def _transaction_nk(self, transaction):
        return [transaction['fields']['account'], transaction['fields']['tx_number']]
    def _error_nk(self, error):
        return [error['fields']['account'], error['fields']['tx_number']]
    def _uh_nk(self, upload_history):
        return [upload_history['fields']['account'], upload_history['fields']['start_date'], upload_history['fields']['end_date']]

    def build_upload_histories(self) :
        # Emulate a set of uploads spaced 30 days apart
        account = self._account[0]
        user = self._user[0]
        for index in range(self._context['num_histories']):
            upload_date = self._context['transaction_start_date'] + td(days=index * 30)
            uh = {'model':'Accounts.uploadhistory',
                  'fields': {'account': self._account_nk(account),
                  'start_date': upload_date.strftime('%Y-%m-%d'),
                  'end_date': (upload_date + td(days=29)).strftime('%Y-%m-%d'),
                  'uploaded_by': [user['fields']['email']],
                  'uploaded_at': (upload_date + td(days=1)).strftime('%Y-%m-%d %H:%MZ'), } }
            self._uploads.append(uh)

    def build_upload_errors(self):
        for upload in self._uploads:
            error_count = random.randint(0, self._context['num_upload_error'])
            txs = [tx for tx in self._transactions if tx['fields']['upload_history'] == self._uh_nk(upload)]
            chosen_txs = random.sample(txs, error_count)
            for tx in chosen_txs:
                # Error causes - No category or wrong category for debit/credit
                reason = random.choice(['No Category', 'Wrong Category'])
                match reason:
                    case 'No Category':
                        self._errors.append({'model':'Accounts.uploaderror',
                               'fields':{'transaction': self._transaction_nk(tx),
                                             'upload_history': self._uh_nk(upload),
                                             'error_message': f'Unknown category specified'
                                             }})
                    case 'Wrong Category':
                       # Find a category with the wrong debit/credit flag
                       new_type = 'C' if Decimal(tx['fields']['debit']) > 0 else 'D'
                       new_category = random.choice([i for i in self._category if i['fields']['credit_debit'] == new_type])
                       tx['fields']['category'] = self._category_nk(new_category)
                       self._errors.append(
                           {'model':'Accounts.uploaderror',
                               'fields':{'transaction': self._transaction_nk(tx),
                                            'upload_history': self._uh_nk(upload),
                                             'error_message': f'Invalid category for debit' if new_type == 'C' else f'Invalid category for credit'
                                            }})

    def build_transactions(self) :
        balance = 0 # make sure it never goes negative
        tx_number = 1
        for uh in self._uploads:
            for index, tx_number in enumerate(range(self._context['num_transactions'])):
                tx_date = datetime.datetime.strptime(uh['fields']['start_date'], '%Y-%m-%d') + td(days=index*(30/self._context['num_histories']) )
                account=self._account[0]
                amount = random.randint(8, 500)
                while True:
                    category = random.choice(self._category)
                    if category['fields']['credit_debit'] == 'D' :
                        if balance - amount < 0:
                            continue
                        else:
                            amount = -amount
                            break
                    else:
                        break
                tx = {'model':'Accounts.transaction',
                      'fields':{'account': self._account_nk(account),
                      'tx_number': tx_number,
                       'transaction_date':tx_date.strftime('%Y-%m-%d'),
                      'description': f'Transaction {tx_number}',
                      'parent': None,
                      'name': f'tx : {tx_number}',
                      'category': self._category_nk(category),
                      'debit': str(-Decimal(str(amount)) if amount < 0 else Decimal('0.00')),
                      'credit': str(Decimal(str(amount)) if amount > 0 else Decimal('0.00')),
                      'upload_history': self._uh_nk(uh),
                      'balance': str(balance + Decimal(str(amount)))
                      }}
                self._transactions.append(tx)
                balance += Decimal(str(amount))
                tx_number += 1

    def generate(self):
        self.build_upload_histories()
        self.build_transactions()
        self.build_upload_errors()

    def dump(self):
        with open(self._context['history_file'], 'w') as f:
            json.dump(self._uploads, f, indent=4)
        with open(self._context['error_file'], 'w') as f:
            json.dump(self._errors, f, indent=4)
        with open(self._context['transaction_file'], 'w') as f:
            json.dump(self._transactions, f, indent=4)

# @click.command()
@click.argument('history_file', type=click.Path(exists=False), default='Accounts/fixtures/upload_errors/ue_upload_history.json')
@click.argument('error_file', type=click.Path(exists=False), default='Accounts/fixtures/upload_errors/ue_upload_errors.json')
@click.argument('transaction_file', type=click.Path(exists=False), default='Accounts/fixtures/upload_errors/ue_transactions.json')
@click.command(help='Build fixtures for upload history, upload errors and transactions.')
@click.option('--verbose', '-v', 'verbosity', is_flag=True, default=False, help='Enable verbose output')
@click.option('-H', 'num_histories', type=int, default=5, help='Number of upload histories to Emulate')
@click.option('-E', 'num_upload_error', type=int, default=3, help='Max Number of errors per upload')
@click.option('-T', 'num_transactions', type=int, default=20, help='Number of transactions per upload')
@click.option('-s', "transaction_start_date", type=click.DateTime(), default='2023-01-01', help='Start date for transactions')
@click.option('-c', 'category_file', type=click.Path(exists=True), default='Accounts/fixtures/account_test_categories.json', help='File containing category data')
@click.option('-u','user_file', type=click.Path(exists=True), default='Accounts/fixtures/account_test_users.json', help='File containing user data')
@click.option('-a','account_file', type=click.Path(exists=True), default='Accounts/fixtures/test_bank_account.json', help='File containing bank_account_data')
@click.pass_context
def main( context, **kwargs):

    context.obj = kwargs

    if context.obj['num_transactions'] < context.obj['num_upload_error']:
        click.echo(f'Error count ({context.obj['num_upload_error']}) cannot be greater than history count ({context.obj['num_transactions']})')
        click.exit(1)

    if context.obj['num_transactions'] < context.obj['num_histories']:
        click.echo(f'Transaction count ({context.obj['num_transactions']}) cannot be less than history count ({context.obj['num_histories']})')
        click.exit(1)

    fixtureGen = GenerateFixture(context)
    fixtureGen.generate()
    fixtureGen.dump()

if __name__ == "__main__":
    main()