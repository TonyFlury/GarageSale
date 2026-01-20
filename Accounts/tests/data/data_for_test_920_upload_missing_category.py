from Accounts.tests.utils import DataStream


def test_data(**kwargs):
    return DataStream(data=[{'name': 'Sarah\'s SweetShop', 'credit': '50.00', 'balance': '50.00', 'category':'Unexpected'},
                            {'name':'Big Company','credit':'500.00', 'balance':'550.00','category':'Sponsorship'}, ],
                             **kwargs)