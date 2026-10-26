from django.apps import AppConfig
from django.db.models.signals import post_migrate

contributor_types = ['sponsor','marketer'] # Eventually this will be data driven.
actions = ['add','change','view','delete']

class ContributorsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'Contributors'

#    def ready(self):
#        from django.contrib.auth.models import Permission
#        from django.contrib.contenttypes.models import ContentType

        # Check or create permissions for the contributor types - so different users have
        # different access to the contributor table.
#        print(f'Creating permissions for {self.name}')
#        ctype = ContentType.objects.get(app=self.name, model='contributor')
#        for action, _type in zip(actions,contributor_types):
#            code_name = f'{action}_{_type}'
#            full_name = f'can {action.capitalize()}  {_type.capitalize()}'
#            Permission.objects.get_or_create(content_type=ctype, codename=code_name, defaults={'name':full_name})
