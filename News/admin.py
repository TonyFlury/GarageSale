from django.contrib import admin
from django import forms

# Register your models here.
from .models import NewsArticle, NewsLetterMailingList


class NewsLetterMailingListForm(forms.ModelForm):
    class Meta:
        model = NewsLetterMailingList
        fields = ['user_email', 'last_sent']


@admin.register(NewsLetterMailingList)
class NewsArticleAdmin(admin.ModelAdmin):
    form = NewsLetterMailingListForm
    list_display = ['user_email', 'last_sent']
    exclude = ['slug']
    date_hierarchy = 'last_sent'


class NewsArticleForm(forms.ModelForm):
    synopsis = forms.CharField( widget=forms.Textarea( attrs={'rows': 3, 'cols': 80}))
    class Meta:
        model = NewsArticle
        exclude = ['slug']


@admin.register(NewsArticle)
class NewsArticleAdmin(admin.ModelAdmin):
    form = NewsArticleForm
    list_display = ['headline', 'publish_by', 'expire_by']
    exclude = ['slug']
    date_hierarchy = 'publish_by'
