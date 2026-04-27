from django import template

import qrcode
import qrcode.image.svg as factories
from django.urls import reverse
from django.utils.safestring import mark_safe

register = template.Library()

@register.simple_tag(takes_context=True)
def qr_from_view(context, view, *args, **kwargs):
    request = context.get('request')
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=0,
        image_factory=factories.SvgPathFillImage,
    )
    uri = request.build_absolute_uri(reverse(view, args=args, kwargs=kwargs))
    qr.add_data(uri)
    qr.make(fit=True)
    return mark_safe(qr.make_image().to_string(encoding="unicode"))

@register.simple_tag(takes_context=True)
def qr_from_object(context, obj):
    if not hasattr(obj, 'get_absolute_url'):
        return None

    request = context.get('request')

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=1,
        image_factory=factories.SvgPathFillImage,
    )
    uri = request.build_absolute_uri(obj.get_absolute_url())
    qr.add_data(uri)
    qr.make(fit=True,)
    img = qr.make_image()
    return mark_safe(img.to_string(encoding="unicode"))