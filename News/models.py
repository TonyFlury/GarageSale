from django.contrib.auth.models import User
from django.db import models
from django.db.models import F, Q
from django_quill.fields import QuillField
from django.utils.text import slugify
from datetime import date


class NewsPageOrder(models.Manager):
    """Manager that returns all news articles in published order"""
    def get_queryset(self):
        return (super().get_queryset().
                filter(publish_by__lte=date.today()).
                filter(Q(expire_by__gte=date.today()) | Q(expire_by__isnull = True)).
                order_by('front_page', '-publish_by'))


class Ticker(NewsPageOrder):
    """Manager for Ticker items only"""
    def get_queryset(self):
        return super().get_queryset().values('slug', 'headline')


class FrontPageOnly(NewsPageOrder):
    """Manager that gives the Front page only articles"""
    def get_queryset(self):
        return super().get_queryset().filter(front_page=True)


# Create your models here.
class NewsArticle(models.Model):
    class Meta:
        permissions = [
            ("create", "create a news article"),
            ("edit", "edit a given news article"),
        ]

    objects = models.Manager()
    FrontPageOrder = FrontPageOnly()
    news_page_order = NewsPageOrder()

    slug = models.SlugField()
    creation_date = models.DateTimeField(auto_now_add=True)
    publish_by = models.DateField(db_index=True, default=date.today)
    expire_by = models.DateField(db_index=True, null=True, blank=True)
    headline = models.CharField(max_length=256)
    front_page = models.BooleanField(default=False, db_index=True)
    content = QuillField(default='')
    synopsis = models.CharField(max_length=256, null=True)

    def save(self, *args, **kwargs):
        if not self.id:
            self.slug = slugify(self.headline)

        super().save(*args, **kwargs)


class NewsLetterMailingList(models.Model):
    user_email= models.EmailField( unique=True )
    last_sent = models.DateField(null=True)
