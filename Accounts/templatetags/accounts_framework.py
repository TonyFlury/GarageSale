from django import template
from django.urls import reverse
from django.utils.html import format_html_join

from Accounts.models import Account, FinancialYear

link_str = '<a href="{}">{}</a>'

register = template.Library()

@register.simple_tag(takes_context=True)
def breadcrumb(context):

    jump_table = {'financial_year': financial_year_breadcrumb, 'transactions':transactions_breadcrumb,
                  'categories' : categories_breadcrumb, 'reports': lambda x: base_breadcrumb(x) + [{'Reports':''}],}
    data_type = context.get('data_type', None)
    action = context.get('action', None)
    print(f"Data type: {data_type}, Action: {action}")
    return format_html_join(' / ', link_str, ((v, k) for d in jump_table.get(data_type, base_breadcrumb)(context) for k, v in d.items() ))

def categories_breadcrumb(context):
    match context.get('action', None) :
        case 'list':
            return  base_breadcrumb(context) + [{'Categories':reverse('Account:CategoryList')}]
        case _:
            return base_breadcrumb(context) + [{'Categories':'Navigation'}]

def base_breadcrumb(context) -> list[dict[str,str]]:
    return [{'Team Pages':reverse('TeamPages:Root')}, {'Financial Data':reverse('Account:EntryPoint')}]

def financial_year_breadcrumb(context):
    content = base_breadcrumb(context)

    match context.get('action', None) :
        case 'list':
            content.append({'Financial Year List':reverse('Account:FinancialYearList')})
        case 'edit':
            content.append({f'Financial Year Editing - {context.get("FinancialYear", None).year}': ''} )
        case 'view':
            content.append({f'Financial Year details - {context.get("FinancialYear", None).year}': ''})
        case _:
            content.append({'Financial Data':'Navigation'})

    return content

def transactions_breadcrumb(context):
    content = base_breadcrumb(context)

    match context.get('action', None) :
        case 'list' if context.get('account_selection', None) and context.get('year_selected', None):
            content.append({f'Transaction List - {Account.objects.get(id=context.get("account_selection", None))!s} - {context.get("year_selected", None)!s}':''})
        case 'list' if context.get('account_selection', None) and not context.get('year_selected', None):
            content.append({f'Transaction List - {Account.objects.get(id=context.get("account_selection", None))!s}':''})
        case 'list' if not context.get('account_selection', None):
            content.append({'Transaction List':''})
        case 'upload':
            content.append({'Transaction Uploads': ''} )
        case 'uploadErrors' if context.get('upload_history', None):
            content.append({f'Upload Errors {context.get("upload_history", None).account.account_name}':''})
        case 'uploadErrors' if not context.get('upload_history', None):
            content.append({f'Upload Errors': ''})
        case _:
            content.append({'Financial Data':'Navigation'})

    return content
