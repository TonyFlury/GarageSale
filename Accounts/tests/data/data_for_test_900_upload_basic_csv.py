from Accounts.tests.utils import DataStream

def test_data( **kwargs):
    return DataStream(data=[{'name': 'Sarah\'s SweetShop', 'credit': '50.00', 'balance': '50.00'}, ], **kwargs)
