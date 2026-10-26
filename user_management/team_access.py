"""Officer-facing membership management; only the listed groups are editable."""
from datetime import timedelta
from smtplib import SMTPException
from uuid import uuid4

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.models import Group
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.views import View

from TeamPageFramework.entry_point import EntryPointMixin
from .models import TeamAccessChange, TeamInvitation, TeamMember

PERMISSION = 'user_management.manage_team_access'
SALT = 'user_management.team_access.review'
ROLE_DESCRIPTIONS = {
    'SponsorshipManager': ('Sponsorship', 'Manage sponsors and record their contributions.'),
    'PrizeAllocationManager': ('Prize allocation', 'Categorise contributions and set the prize order.'),
    'CraftMarketManager': ('Craft market', 'Manage market traders and their participation.'),
    'Financier': ('Finance', 'Work with the event accounts and financial records.'),
}
MEMBERSHIPS = [('ordinary', 'Ordinary user'), ('volunteer', 'Volunteer'), ('exec', 'Exec member'), ('officer', 'Officer')]
MANAGED_GROUPS = {'Volunteer', 'ExecMember', 'Officer', *ROLE_DESCRIPTIONS}


def group_names(user):
    return sorted(user.groups.values_list('name', flat=True))


def membership(names):
    return 'officer' if 'Officer' in names else 'exec' if 'ExecMember' in names else 'volunteer' if 'Volunteer' in names else 'ordinary'


def protected(user):
    return user.is_staff or user.is_superuser or user.groups.filter(name='WebAdmin').exists()


def snapshot(user):
    return {'groups': group_names(user), 'staff': user.is_staff, 'superuser': user.is_superuser,
            'active': user.is_active, 'guest': user.is_guest, 'verified': user.is_verified,
            'email': user.email,
            'permissions': sorted(user.user_permissions.values_list('pk', flat=True))}


class AccessForm(forms.Form):
    membership = forms.ChoiceField(choices=MEMBERSHIPS, widget=forms.RadioSelect, label='Team membership')
    roles = forms.MultipleChoiceField(required=False, widget=forms.CheckboxSelectMultiple, label='Responsibilities')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        available = set(Group.objects.filter(name__in=ROLE_DESCRIPTIONS).values_list('name', flat=True))
        self.fields['roles'].choices = [(key, label) for key, (label, _) in ROLE_DESCRIPTIONS.items() if key in available]

    def clean(self):
        data = super().clean()
        if data.get('membership') == 'volunteer' and data.get('roles'):
            self.add_error('roles', 'Volunteers have a profile only. Clear the responsibilities or choose another membership.')
        return data


class InviteForm(AccessForm):
    email = forms.EmailField(label='Email address')
    first_name = forms.CharField(max_length=150, label='First name')
    last_name = forms.CharField(max_length=150, label='Last name')

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if get_user_model().objects.filter(email__iexact=email).exists():
            raise ValidationError('This person already has an account. Find them on the Manage team access page instead.')
        return email


def desired_groups(data):
    names = set(data['roles'])
    if data['membership'] in ('exec', 'officer'):
        names.add('ExecMember')
    if data['membership'] == 'officer':
        names.add('Officer')
    if data['membership'] == 'volunteer':
        names.add('Volunteer')
    return names


def validate_volunteer_group():
    group = Group.objects.filter(name='Volunteer').first()
    if group is None:
        raise ValidationError('The Volunteer group is not configured. Apply the volunteer profile migration first.')
    allowed = {('user_management', 'manage_own_profile'), ('GarageSale', 'manage_own_team_profile')}
    grants = set(group.permissions.values_list('content_type__app_label', 'codename'))
    if not grants or not grants <= allowed:
        raise ValidationError('The Volunteer group has unexpected permissions. Ask an administrator to review it before assigning this membership.')


def audit(actor, user, action, before):
    TeamAccessChange.objects.create(actor=actor, subject=user, actor_email=actor.email,
                                   subject_email=user.email, action=action,
                                   before_groups=before, after_groups=group_names(user))


def send_invitation(request, invitation):
    url = request.build_absolute_uri(reverse('user_management:team_invitation', args=[invitation.token]))
    sender = settings.APPS_SETTINGS.get('user_management', {}).get('EMAIL_SENDER') or settings.DEFAULT_FROM_EMAIL
    sent = send_mail('Your Brantham Garage Sale team invitation',
                    f'Hello {invitation.user.first_name},\n\nYou have been invited to the Brantham Garage Sale website. '
                    f'Set your own password using this link:\n{url}\n\nThis link expires in 7 days. '
                    'If you were not expecting this invitation, you can ignore it.',
                    sender, [invitation.user.email])
    if sent != 1:
        raise OSError('Invitation email was not sent.')


class AccessMixin(LoginRequiredMixin, PermissionRequiredMixin):
    permission_required = PERMISSION
    login_url = 'user_management:login'


class TeamAccessList(EntryPointMixin, AccessMixin, View):
    entry_point_label = 'Manage team access'
    entry_point_url = 'user_management:team_access'
    entry_point_permission = PERMISSION
    entry_point_needs_event = False
    entry_point_icon = static('user_management/images/icons/team-access.svg')

    def get(self, request):
        query = request.GET.get('q', '').strip()[:150]
        search_all = request.GET.get('scope') == 'all'
        users = get_user_model().objects.all().prefetch_related('groups').order_by('first_name', 'last_name', 'email')
        if not search_all:
            users = users.filter(groups__isnull=False).distinct()
        elif not query:
            users = users.none()
        if query:
            users = users.filter(Q(email__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query))
        page = Paginator(users, 20).get_page(request.GET.get('page'))
        rows = [{'person': person, 'groups': group_names(person), 'protected': protected(person)} for person in page]
        return TemplateResponse(request, 'team_access/list.html', {
            'rows': rows, 'page': page, 'query': query, 'search_all': search_all,
        })


class TeamAccessEdit(AccessMixin, View):
    def get(self, request, user_id=None):
        user = get_object_or_404(get_user_model(), pk=user_id) if user_id else None
        if user and protected(user):
            raise PermissionDenied('Administrator accounts are managed separately in Django admin.')
        names = group_names(user) if user else []
        form = AccessForm(initial={'membership': membership(names), 'roles': list(set(names) & ROLE_DESCRIPTIONS.keys())}) if user else InviteForm(initial={'membership': 'ordinary'})
        return self.render(request, form, user)

    def render(self, request, form, user, **extra):
        choices = dict(form.fields['roles'].choices)
        roles = [{'field': field, 'description': ROLE_DESCRIPTIONS[field.data['value']][1]} for field in form['roles']]
        unavailable = [label for key, (label, _) in ROLE_DESCRIPTIONS.items() if key not in choices]
        return TemplateResponse(request, 'team_access/edit.html', {
            'form': form, 'person': user, 'role_options': roles, 'unavailable': unavailable,
            'history': user.team_access_changes.select_related('actor')[:10] if user else [], **extra,
        })

    def post(self, request, user_id=None):
        user = get_object_or_404(get_user_model(), pk=user_id) if user_id else None
        if user and protected(user):
            raise PermissionDenied('Administrator accounts are managed separately in Django admin.')
        token = request.POST.get('review_token')
        if token:
            try:
                payload = signing.loads(token, salt=SALT, max_age=1200)
                if payload['actor'] != request.user.pk or payload['user'] != user_id:
                    raise signing.BadSignature()
            except (signing.BadSignature, KeyError, TypeError):
                messages.error(request, 'This review has expired or is invalid. Review the access choices again.')
                return redirect(request.path)
            form = AccessForm(payload['data']) if user else InviteForm(payload['data'])
            if request.POST.get('action') == 'back':
                return self.render(request, form, user)
            if request.POST.get('action') != 'save':
                raise PermissionDenied('Review the changes before saving.')
        else:
            form = AccessForm(request.POST) if user else InviteForm(request.POST)
        if not form.is_valid():
            return self.render(request, form, user)
        data = form.cleaned_data
        desired = desired_groups(data)
        if user and data['membership'] == 'volunteer' and (
                set(group_names(user)) - MANAGED_GROUPS or user.user_permissions.exists()):
            form.add_error('membership', 'This account has other groups or individually assigned permissions. '
                           'Ask an administrator to review those before assigning Volunteer membership.')
            return self.render(request, form, user)
        if user and user.pk == request.user.pk and ('Officer' in group_names(user)) != ('Officer' in desired):
            form.add_error('membership', 'Ask another officer to change your Officer membership.')
            return self.render(request, form, user)
        if not token:
            before = snapshot(user) if user else None
            payload = {'actor': request.user.pk, 'user': user_id, 'data': data, 'before': before}
            old_names = set(before['groups']) if before else set()
            after = (old_names - MANAGED_GROUPS) | desired
            return self.render(request, form, user, reviewing=True,
                               review_token=signing.dumps(payload, salt=SALT),
                               added=sorted(after - old_names), removed=sorted(old_names - after),
                               resulting_membership=dict(MEMBERSHIPS)[data['membership']],
                               resulting_roles=[ROLE_DESCRIPTIONS[key][0] for key in data['roles']],
                               unchanged=sorted(old_names - MANAGED_GROUPS),
                               direct_permissions=user.user_permissions.exists() if user else False)
        try:
            with transaction.atomic():
                # One lock serialises officer promotions/demotions and last-officer checks.
                officer_group, _ = Group.objects.get_or_create(name='Officer')
                Group.objects.select_for_update().get(pk=officer_group.pk)
                actor = get_user_model().objects.get(pk=request.user.pk)
                if not actor.has_perm(PERMISSION):
                    raise PermissionDenied('Your permission to manage team access has changed.')
                if user:
                    user = get_user_model().objects.select_for_update().get(pk=user_id)
                    if snapshot(user) != payload['before']:
                        raise ValidationError('This account changed after your review. Reload and review it again.')
                    if protected(user):
                        raise PermissionDenied()
                    before = group_names(user)
                    if 'Officer' in before and 'Officer' not in desired and user.is_active:
                        others = get_user_model().objects.filter(
                            groups=officer_group, is_active=True, is_verified=True, is_guest=False,
                        ).exclude(pk=user.pk).exclude(password__startswith='!')
                        if not others.exists():
                            raise ValidationError('Keep at least one active Officer. Appoint another Officer before removing this membership.')
                else:
                    user = get_user_model().objects.create_user(email=data['email'], first_name=data['first_name'], last_name=data['last_name'])
                    before = []
                if data['membership'] == 'volunteer':
                    validate_volunteer_group()
                for name in desired & {'ExecMember', 'Officer'}:
                    Group.objects.get_or_create(name=name)
                user.groups.remove(*Group.objects.filter(name__in=MANAGED_GROUPS - desired))
                user.groups.add(*Group.objects.filter(name__in=desired))
                if data['membership'] == 'volunteer':
                    profile = TeamMember.objects.filter(user=user).first()
                    if profile is None:
                        TeamMember.objects.create(user=user, role='Volunteer')
                    elif profile.role != 'Volunteer':
                        profile.role = 'Volunteer'
                        profile.save(update_fields=['role', 'updated_at'])
                audit(actor, user, 'access_changed' if user_id else 'invited', before)
                if not user_id:
                    invitation = TeamInvitation.objects.create(user=user, expires_at=timezone.now() + timedelta(days=7))
                    send_invitation(request, invitation)
        except (ValidationError, IntegrityError, SMTPException, OSError) as error:
            text = error.messages[0] if isinstance(error, ValidationError) else 'Nothing was saved. The account could not be saved or the invitation email could not be sent. Please try again.'
            form.add_error(None, text)
            return self.render(request, form, user if user_id else None)
        messages.success(request, 'Access updated.' if user_id else 'Invitation sent. They can now choose their own password.')
        return redirect('user_management:team_access')


class TeamInvitationResend(AccessMixin, View):
    def post(self, request, user_id):
        try:
            with transaction.atomic():
                user = get_object_or_404(get_user_model().objects.select_for_update(), pk=user_id)
                if protected(user):
                    raise PermissionDenied()
                invitation = get_object_or_404(TeamInvitation.objects.select_for_update(), user=user, accepted_at__isnull=True)
                if user.has_usable_password() or user.is_verified:
                    raise PermissionDenied('This account has already been activated.')
                invitation.token = uuid4()
                invitation.expires_at = timezone.now() + timedelta(days=7)
                invitation.save()
                send_invitation(request, invitation)
                audit(request.user, user, 'invitation_resent', group_names(user))
            messages.success(request, 'A fresh invitation has been sent. The previous link no longer works.')
        except (SMTPException, OSError):
            messages.error(request, 'The invitation could not be sent. Please try again; the previous link is unchanged.')
        return redirect('user_management:team_access_edit', user_id=user_id)


class TeamInvitationAccept(View):
    def dispatch(self, request, token):
        self.invitation = get_object_or_404(TeamInvitation.objects.select_related('user'), token=token)
        if self.invitation.accepted_at or self.invitation.expires_at <= timezone.now():
            return TemplateResponse(request, 'team_access/accept.html', {'expired': True}, status=410)
        return super().dispatch(request, token=token)

    def get(self, request, token):
        return TemplateResponse(request, 'team_access/accept.html', {'form': SetPasswordForm(self.invitation.user), 'invited_user': self.invitation.user})

    def post(self, request, token):
        with transaction.atomic():
            user = get_user_model().objects.select_for_update().get(pk=self.invitation.user_id)
            invitation = TeamInvitation.objects.select_for_update().get(pk=self.invitation.pk)
            if invitation.token != token or invitation.accepted_at or invitation.expires_at <= timezone.now() or not user.is_active or protected(user):
                return TemplateResponse(request, 'team_access/accept.html', {'expired': True}, status=410)
            form = SetPasswordForm(user, request.POST)
            if form.is_valid():
                form.save()
                user.is_verified = True
                user.is_guest = False
                user.save(update_fields=['is_verified', 'is_guest'])
                invitation.accepted_at = timezone.now()
                invitation.save(update_fields=['accepted_at'])
                audit(user, user, 'invitation_accepted', group_names(user))
                return TemplateResponse(request, 'team_access/accept.html', {'complete': True})
        return TemplateResponse(request, 'team_access/accept.html', {'form': form, 'invited_user': user})
