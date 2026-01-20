from datetime import date, timedelta as td

from Accounts.tests.utils import DataStream

def test_data(data_batch='A',**kwargs ):
    match data_batch:
        case 'A':
            tx_date = date.today() - td(days=100)
            return DataStream(data=[{'date':tx_date, 'name': 'Sarah\'s SweetShop', 'credit': '50.00', 'balance': '50.00'},
                            {'date':tx_date + td(days=1), 'name':'Big Company','credit':'100.00', 'balance':'150.00','category':'Sponsorship'}, ],
                             **kwargs)
        case 'B':
            tx_date = date.today() - td(days=90)
            return DataStream(data=[{'date':tx_date, 'name': 'Petes Photo Workshop', 'credit': '500.00', 'balance': '650.00'},
                            {'date':tx_date + td(days=1), 'name':'Bammer Guy\'s','debit':'50.00', 'balance':'600.00','category':'Advertisement'}, ],
                             **kwargs)
        case 'C':
            tx_date = date.today() - td(days=80)
            return DataStream(data=[{'date':tx_date, 'name': 'Mr Smith', 'credit': '8.00', 'balance': '608.00'},
                            {'date':tx_date + td(days=1), 'name':'Mr Jones','credit':'11.00', 'balance':'618.00','category':'Sale'}, ],
                             **kwargs)
        case _:
            return DataStream(data=[], **kwargs)
