import datetime

from django.db import models

from django.db.models import  Q, DEFERRED
from django_quill.fields import QuillField
from datetime import date
from django.utils.text import slugify


class NewsPageOrder(models.Manager):
    """Manager that returns all news articles in published order"""

    def get_queryset(self):
        return (super().get_queryset().
                filter(publish_by__lte=date.today()).
                filter(Q(expire_by__gte=date.today()) | Q(expire_by__isnull=True)).
                filter(published=True).
                order_by('front_page', '-publish_by'))


class NewsQuerySet(models.query.QuerySet):
    def published_and_unpublished(self):
        return self.filter(Q(published=True) | Q(published=False))

    def unpublished_only(self):
        return self.filter(published=False)

    def published_only(self):
        return self.filter(published=True)

    def exclude_published(self):
        return self.exclude(published=True)

    def expired(self):
        return self.filter(Q(expire_by__gte=date.today()) & Q(expire_by__isnull=False))

    def past_publish_by(self):
        return self.filter(publish_by__lte=date.today())

    def sort_by_normal(self):
        return self.order_by('front_page', '-publish_by')


class Ticker(NewsPageOrder):
    """Manager for Ticker items only"""

    def get_queryset(self):
        return super().get_queryset().values('slug', 'headline')


class FrontPageOnly(NewsPageOrder):
    """Manager that gives the Front page only articles"""

    def get_queryset(self):
        return super().get_queryset().filter(front_page=True)


class Expired(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(expire_by__lt=date.today()).order_by('expire_by')


class UnPublished(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(published=False).order_by('publish_by')


# Create your models here.
class NewsArticle(models.Model):
    objects = models.Manager()
    FrontPageOrder = FrontPageOnly()
    news_page_order = NewsPageOrder()
    chainable = NewsQuerySet.as_manager()

    slug = models.SlugField()
    creation_date = models.DateTimeField(auto_now_add=True)
    publish_by = models.DateField(db_index=True, default=date.today)
    expire_by = models.DateField(db_index=True, null=True, blank=True)
    headline = models.CharField(max_length=256)
    front_page = models.BooleanField(default=False, db_index=True)
    content = QuillField(default='')
    synopsis = models.CharField(max_length=256, null=True, blank=True)
    published = models.BooleanField(default=False)

    class Meta:
        fields = "__all__"

    @property
    def is_live(self):
        """Is this item live (ie visible to user)
           i.e. The published flag is set and it is between the publish_by and expire_by dates
        """
        return (self.published and
                ((self.expire_by is not None and self.publish_by <= datetime.date.today() <= self.expire_by) or
                 (self.expire_by is None and self.publish_by <= datetime.date.today())))

    def save(self, force_insert=False, force_update=False,
             using=None,
             update_fields=None,
             ):

        self.slug = slugify(self.headline)
        if update_fields is not None and ('headline' not in update_fields or 'slug' not in update_fields):
            update_fields = {'headline', 'slug'}.union(update_fields)

        return super().save(force_insert=force_insert, force_update=force_update, using=using,
                            update_fields=update_fields)

    @property
    def can_be_published(self):
        """ return True if this article can be published
            ie currently un-published and not expired
        """
        return not self.published and (self.expire_by is None or self.expire_by > datetime.date.today())

    class Meta:
        default_permissions = ()
        permissions = [
            ("can_manage_news", "Can manage the news Articles"),
            ("can_create_news", "Can create a news Article"),
            ("can_publish_news", "Can publish a news Article"),
            ("can_edit_news", "Can edit a news Article"),
            ("can_view_news", "Can view a news Article"),
            ("can_delete_news", "Can delete a news Article")
        ]


class NewsLetterMailingList(models.Model):
    user_email = models.EmailField(unique=True)
    last_sent = models.DateField(null=True)
