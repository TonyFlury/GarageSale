from django.shortcuts import render

# Create your views here.

from django.views import View
from .forms import NewsArticle as NewsForm
from .models import NewsArticle as NewsModel, NewsLetterMailingList
from django.shortcuts import get_object_or_404, render, redirect
from django.http import HttpResponseServerError, HttpRequest


def publish_news(request, news_id):
    """Change the published status of the given article
       There are no safeguards on the view - they are done via the GUI
       Essentially :
            An article can be published if can_be_published is True
            An article can only be unpublished if it is already published
    """
    try:
        article = NewsModel.objects.get( id = news_id)
    except NewsModel.DoesNotExist:
        return HttpResponseServerError(f'News item does not exist {news_id}')

    article.published = not article.published
    article.save()
    return


def news_page(request):
    qs = NewsModel.news_page_order.all()
    return render(request, template_name='news_page.html', context={'articles': qs})


def news_letter_subscribe(request : HttpRequest):
    if request.method != "POST":
        return HttpResponseServerError("news_letter_subscribe : expecting a POST action")

    action = request.POST.get('action', None)
    user = request.user

    qs = NewsLetterMailingList.objects.filter(user_email=user.email)
    match action:
        case "Subscribe":
            if len(qs) == 0:
                inst = NewsLetterMailingList(user_email=user.email, last_sent=None)
                inst.save()
            return redirect("getInvolved")
        case "UnSubscribe":
            if len(qs) == 1:
                inst = qs[0]
                inst.delete()
            return redirect("getInvolved")
        case "_":
            return HttpResponseServerError(f'news_letter_subscribe : unexpected value {action} for action field')


class Article(View):
    form = NewsForm

    def get(self, request, slug=None, *args, **kwargs):
        if slug is not None:
            article = get_object_or_404( NewsModel, slug=slug)
            return render(request, template_name='news_article.html', context={'article': article})

        return HttpResponseServerError()

