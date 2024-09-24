from django.conf import settings # import the settings file


def test_server(request):
    # return the value you want as a dictionary. you may add multiple values in there.
    return {'TEST_SERVER': settings.TEST_SERVER}
