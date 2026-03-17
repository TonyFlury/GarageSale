
from django.http import HttpResponse, HttpResponseServerError
from django.shortcuts import render, reverse, redirect
from django.templatetags.static import static

from TeamPageFramework.entry_point import EntryPointMixin, register

from Accounts.models import Categories

register(label='Categories', url_path='Account:CategoryList', icon_path=static('Accounts/images/icons/navigation/category-svgrepo-com.svg'),
          permission='Accounts.view_category',
          needs_event=False, nav_page='AccountsEntryPoint')
def category_list(request):
    categories = Categories.objects.filter(parent=None)
    return render(request,'Categories/base_category_list.html', {'categories':categories, 'data_type':'categories', 'action':'list'})