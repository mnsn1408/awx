# Python LDAP
import ldap

# Django
from django.utils.translation import ugettext_lazy as _

# Django Auth LDAP
import django_auth_ldap.config
from django_auth_ldap.config import LDAPSearch, LDAPSearchUnion

# Tower
from awx.conf import fields
from awx.conf.fields import *  # noqa
from awx.conf.license import feature_enabled
from awx.main.validators import validate_certificate
from awx.sso.validators import *  # noqa


def get_subclasses(cls):
    for subclass in cls.__subclasses__():
        for subsubclass in get_subclasses(subclass):
            yield subsubclass
        yield subclass


class AuthenticationBackendsField(fields.StringListField):

    # Mapping of settings that must be set in order to enable each
    # authentication backend.
    REQUIRED_BACKEND_SETTINGS = collections.OrderedDict([
        ('awx.sso.backends.LDAPBackend', [
            'AUTH_LDAP_SERVER_URI',
        ]),
        ('awx.sso.backends.RADIUSBackend', [
            'RADIUS_SERVER',
        ]),
        ('social.backends.google.GoogleOAuth2', [
            'SOCIAL_AUTH_GOOGLE_OAUTH2_KEY',
            'SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET',
        ]),
        ('social.backends.github.GithubOAuth2', [
            'SOCIAL_AUTH_GITHUB_KEY',
            'SOCIAL_AUTH_GITHUB_SECRET',
        ]),
        ('social.backends.github.GithubOrganizationOAuth2', [
            'SOCIAL_AUTH_GITHUB_ORG_KEY',
            'SOCIAL_AUTH_GITHUB_ORG_SECRET',
            'SOCIAL_AUTH_GITHUB_ORG_NAME',
        ]),
        ('social.backends.github.GithubTeamOAuth2', [
            'SOCIAL_AUTH_GITHUB_TEAM_KEY',
            'SOCIAL_AUTH_GITHUB_TEAM_SECRET',
            'SOCIAL_AUTH_GITHUB_TEAM_ID',
        ]),
        ('awx.sso.backends.SAMLAuth', [
            'SOCIAL_AUTH_SAML_SP_ENTITY_ID',
            'SOCIAL_AUTH_SAML_SP_PUBLIC_CERT',
            'SOCIAL_AUTH_SAML_SP_PRIVATE_KEY',
            'SOCIAL_AUTH_SAML_ORG_INFO',
            'SOCIAL_AUTH_SAML_TECHNICAL_CONTACT',
            'SOCIAL_AUTH_SAML_SUPPORT_CONTACT',
            'SOCIAL_AUTH_SAML_ENABLED_IDPS',
        ]),
        ('django.contrib.auth.backends.ModelBackend', []),
    ])

    REQUIRED_BACKEND_FEATURE = {
        'awx.sso.backends.LDAPBackend': 'ldap',
        'awx.sso.backends.RADIUSBackend': 'enterprise_auth',
        'awx.sso.backends.SAMLAuth': 'enterprise_auth',
    }

    @classmethod
    def get_all_required_settings(cls):
        all_required_settings = set(['LICENSE'])
        for required_settings in cls.REQUIRED_BACKEND_SETTINGS.values():
            all_required_settings.update(required_settings)
        return all_required_settings

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('default', self._default_from_required_settings)
        super(AuthenticationBackendsField, self).__init__(*args, **kwargs)

    def _default_from_required_settings(self):
        from django.conf import settings
        try:
            backends = settings._awx_conf_settings._get_default('AUTHENTICATION_BACKENDS')
        except AttributeError:
            backends = self.REQUIRED_BACKEND_SETTINGS.keys()
        # Filter which authentication backends are enabled based on their
        # required settings being defined and non-empty. Also filter available
        # backends based on license features.
        for backend, required_settings in self.REQUIRED_BACKEND_SETTINGS.items():
            if backend not in backends:
                continue
            required_feature = self.REQUIRED_BACKEND_FEATURE.get(backend, '')
            if not required_feature or feature_enabled(required_feature):
                if all([getattr(settings, rs, None) for rs in required_settings]):
                    continue
            backends = filter(lambda x: x != backend, backends)
        return backends


class LDAPConnectionOptionsField(fields.DictField):

    default_error_messages = {
        'invalid_options': _('Invalid connection option(s): {invalid_options}.'),
    }

    def to_representation(self, value):
        value = value or {}
        opt_names = ldap.OPT_NAMES_DICT
        # Convert integer options to their named constants.
        repr_value = {}
        for opt, opt_value in value.items():
            if opt in opt_names:
                repr_value[opt_names[opt]] = opt_value
        return repr_value

    def to_internal_value(self, data):
        data = super(LDAPConnectionOptionsField, self).to_internal_value(data)
        valid_options = dict([(v, k) for k, v in ldap.OPT_NAMES_DICT.items()])
        invalid_options = set(data.keys()) - set(valid_options.keys())
        if invalid_options:
            options_display = json.dumps(list(invalid_options)).lstrip('[').rstrip(']')
            self.fail('invalid_options', invalid_options=options_display)
        # Convert named options to their integer constants.
        internal_data = {}
        for opt_name, opt_value in data.items():
            internal_data[valid_options[opt_name]] = opt_value
        return internal_data


class LDAPDNField(fields.CharField):

    def __init__(self, **kwargs):
        super(LDAPDNField, self).__init__(**kwargs)
        self.validators.append(validate_ldap_dn)


class LDAPDNWithUserField(fields.CharField):

    def __init__(self, **kwargs):
        super(LDAPDNWithUserField, self).__init__(**kwargs)
        self.validators.append(validate_ldap_dn_with_user)


class LDAPFilterField(fields.CharField):

    def __init__(self, **kwargs):
        super(LDAPFilterField, self).__init__(**kwargs)
        self.validators.append(validate_ldap_filter)


class LDAPFilterWithUserField(fields.CharField):

    def __init__(self, **kwargs):
        super(LDAPFilterWithUserField, self).__init__(**kwargs)
        self.validators.append(validate_ldap_filter_with_user)


class LDAPScopeField(fields.ChoiceField):

    def __init__(self, choices=None, **kwargs):
        choices = choices or [
            ('SCOPE_BASE', _('Base')),
            ('SCOPE_ONELEVEL', _('One Level')),
            ('SCOPE_SUBTREE', _('Subtree')),
        ]
        super(LDAPScopeField, self).__init__(choices, **kwargs)

    def to_representation(self, value):
        for choice in self.choices.keys():
            if value == getattr(ldap, choice):
                return choice
        return super(LDAPScopeField, self).to_representation(value)

    def to_internal_value(self, data):
        value = super(LDAPScopeField, self).to_internal_value(data)
        return getattr(ldap, value)


class LDAPSearchField(fields.ListField):

    default_error_messages = {
        'invalid_length': _('Expected a list of three items but got {length} instead.'),
        'type_error': _('Expected an instance of LDAPSearch but got {input_type} instead.'),
    }
    ldap_filter_field_class = LDAPFilterField

    def to_representation(self, value):
        if not value:
            return []
        if not isinstance(value, LDAPSearch):
            self.fail('type_error', input_type=type(value))
        return [
            LDAPDNField().to_representation(value.base_dn),
            LDAPScopeField().to_representation(value.scope),
            self.ldap_filter_field_class().to_representation(value.filterstr),
        ]

    def to_internal_value(self, data):
        data = super(LDAPSearchField, self).to_internal_value(data)
        if len(data) == 0:
            return None
        if len(data) != 3:
            self.fail('invalid_length', length=len(data))
        return LDAPSearch(
            LDAPDNField().run_validation(data[0]),
            LDAPScopeField().run_validation(data[1]),
            self.ldap_filter_field_class().run_validation(data[2]),
        )


class LDAPSearchWithUserField(LDAPSearchField):

    ldap_filter_field_class = LDAPFilterWithUserField


class LDAPSearchUnionField(fields.ListField):

    default_error_messages = {
        'type_error': _('Expected an instance of LDAPSearch or LDAPSearchUnion but got {input_type} instead.'),
    }
    ldap_search_field_class = LDAPSearchWithUserField

    def to_representation(self, value):
        if not value:
            return []
        elif isinstance(value, LDAPSearchUnion):
            return [self.ldap_search_field_class().to_representation(s) for s in value.searches]
        elif isinstance(value, LDAPSearch):
            return self.ldap_search_field_class().to_representation(value)
        else:
            self.fail('type_error', input_type=type(value))

    def to_internal_value(self, data):
        data = super(LDAPSearchUnionField, self).to_internal_value(data)
        if len(data) == 0:
            return None
        if len(data) == 3 and isinstance(data[0], basestring):
            return self.ldap_search_field_class().run_validation(data)
        else:
            return LDAPSearchUnion(*[self.ldap_search_field_class().run_validation(x) for x in data])


class LDAPUserAttrMapField(fields.DictField):

    default_error_messages = {
        'invalid_attrs': _('Invalid user attribute(s): {invalid_attrs}.'),
    }
    valid_user_attrs = {'first_name', 'last_name', 'email'}
    child = fields.CharField()

    def to_internal_value(self, data):
        data = super(LDAPUserAttrMapField, self).to_internal_value(data)
        invalid_attrs = (set(data.keys()) - self.valid_user_attrs)
        if invalid_attrs:
            attrs_display = json.dumps(list(invalid_attrs)).lstrip('[').rstrip(']')
            self.fail('invalid_attrs', invalid_attrs=attrs_display)
        return data


class LDAPGroupTypeField(fields.ChoiceField):

    default_error_messages = {
        'type_error': _('Expected an instance of LDAPGroupType but got {input_type} instead.'),
    }

    def __init__(self, choices=None, **kwargs):
        group_types = get_subclasses(django_auth_ldap.config.LDAPGroupType)
        choices = choices or [(x.__name__, x.__name__) for x in group_types]
        super(LDAPGroupTypeField, self).__init__(choices, **kwargs)

    def to_representation(self, value):
        if not value:
            return ''
        if not isinstance(value, django_auth_ldap.config.LDAPGroupType):
            self.fail('type_error', input_type=type(value))
        return value.__class__.__name__

    def to_internal_value(self, data):
        data = super(LDAPGroupTypeField, self).to_internal_value(data)
        if not data:
            return None
        return getattr(django_auth_ldap.config, data)()


class LDAPUserFlagsField(fields.DictField):

    default_error_messages = {
        'invalid_flag': _('Invalid user flag: "{invalid_flag}".'),
    }
    valid_user_flags = {'is_superuser'}
    child = LDAPDNField()

    def to_internal_value(self, data):
        data = super(LDAPUserFlagsField, self).to_internal_value(data)
        invalid_flags = (set(data.keys()) - self.valid_user_flags)
        if invalid_flags:
            self.fail('invalid_flag', invalid_flag=list(invalid_flags)[0])
        return data


class LDAPDNMapField(fields.ListField):

    default_error_messages = {
        'type_error': _('Expected None, True, False, a string or list of strings but got {input_type} instead.'),
    }
    child = LDAPDNField()

    def to_representation(self, value):
        if isinstance(value, (list, tuple)):
            return super(LDAPDNMapField, self).to_representation(value)
        elif value in fields.NullBooleanField.TRUE_VALUES:
            return True
        elif value in fields.NullBooleanField.FALSE_VALUES:
            return False
        elif value in fields.NullBooleanField.NULL_VALUES:
            return None
        elif isinstance(value, basestring):
            return self.child.to_representation(value)
        else:
            self.fail('type_error', input_type=type(value))

    def to_internal_value(self, data):
        if isinstance(data, (list, tuple)):
            return super(LDAPDNMapField, self).to_internal_value(data)
        elif data in fields.NullBooleanField.TRUE_VALUES:
            return True
        elif data in fields.NullBooleanField.FALSE_VALUES:
            return False
        elif data in fields.NullBooleanField.NULL_VALUES:
            return None
        elif isinstance(data, basestring):
            return self.child.run_validation(data)
        else:
            self.fail('type_error', input_type=type(data))


class BaseDictWithChildField(fields.DictField):

    default_error_messages = {
        'missing_keys': _('Missing key(s): {missing_keys}.'),
        'invalid_keys': _('Invalid key(s): {invalid_keys}.'),
    }
    child_fields = {
        # 'key': fields.ChildField(),
    }
    allow_unknown_keys = False

    def to_representation(self, value):
        value = super(BaseDictWithChildField, self).to_representation(value)
        for k, v in value.items():
            child_field = self.child_fields.get(k, None)
            if child_field:
                value[k] = child_field.to_representation(v)
            elif allow_unknown_keys:
                value[k] = v
        return value

    def to_internal_value(self, data):
        data = super(BaseDictWithChildField, self).to_internal_value(data)
        missing_keys = set()
        for key, child_field in self.child_fields.items():
            if not child_field.required:
                continue
            elif key not in data:
                missing_keys.add(key)
        if missing_keys:
            keys_display = json.dumps(list(missing_keys)).lstrip('[').rstrip(']')
            self.fail('missing_keys', missing_keys=keys_display)
        if not self.allow_unknown_keys:
            invalid_keys = set(data.keys()) - set(self.child_fields.keys())
            if invalid_keys:
                keys_display = json.dumps(list(invalid_keys)).lstrip('[').rstrip(']')
                self.fail('invalid_keys', invalid_keys=keys_display)
        for k, v in data.items():
            child_field = self.child_fields.get(k, None)
            if child_field:
                data[k] = child_field.run_validation(v)
            elif self.allow_unknown_keys:
                data[k] = v
        return data


class LDAPSingleOrganizationMapField(BaseDictWithChildField):

    default_error_messages = {
        'invalid_keys': _('Invalid key(s) for organization map: {invalid_keys}.'),
    }
    child_fields = {
        'admins': LDAPDNMapField(allow_null=True, required=False),
        'users': LDAPDNMapField(allow_null=True, required=False),
        'remove_admins': fields.BooleanField(required=False),
        'remove_users': fields.BooleanField(required=False),
    }


class LDAPOrganizationMapField(fields.DictField):

    child = LDAPSingleOrganizationMapField()


class LDAPSingleTeamMapField(BaseDictWithChildField):

    default_error_messages = {
        'missing_keys': _('Missing required key for team map: {invalid_keys}.'),
        'invalid_keys': _('Invalid key(s) for team map: {invalid_keys}.'),
    }
    child_fields = {
        'organization': fields.CharField(),
        'users': LDAPDNMapField(allow_null=True, required=False),
        'remove': fields.BooleanField(required=False),
    }


class LDAPTeamMapField(fields.DictField):

    child = LDAPSingleTeamMapField()


class RADIUSSecretField(fields.CharField):

    def to_internal_value(self, value):
        value = super(RADIUSSecretField, self).to_internal_value(value)
        if isinstance(value, unicode):
            value = value.encode('utf-8')
        return value


class SocialMapStringRegexField(fields.CharField):

    def to_representation(self, value):
        if isinstance(value, type(re.compile(''))):
            flags = []
            if value.flags & re.I:
                flags.append('i')
            if value.flags & re.M:
                flags.append('m')
            return '/{}/{}'.format(value.pattern, ''.join(flags))
        else:
            return super(SocialMapStringRegexField, self).to_representation(value)

    def to_internal_value(self, data):
        data = super(SocialMapStringRegexField, self).to_internal_value(data)
        match = re.match(r'^/(?P<pattern>.*)/(?P<flags>[im]+)?$', data)
        if match:
            flags = 0
            if match.group('flags'):
                if 'i' in match.group('flags'):
                    flags |= re.I
                if 'm' in match.group('flags'):
                    flags |= re.M
            try:
                return re.compile(match.group('pattern'), flags)
            except re.error as e:
                raise ValidationError('{}: {}'.format(e, data))
        return data


class SocialMapField(fields.ListField):

    default_error_messages = {
        'type_error': _('Expected None, True, False, a string or list of strings but got {input_type} instead.'),
    }
    child = SocialMapStringRegexField()

    def to_representation(self, value):
        if isinstance(value, (list, tuple)):
            return super(SocialMapField, self).to_representation(value)
        elif value in fields.NullBooleanField.TRUE_VALUES:
            return True
        elif value in fields.NullBooleanField.FALSE_VALUES:
            return False
        elif value in fields.NullBooleanField.NULL_VALUES:
            return None
        elif isinstance(value, (basestring, type(re.compile('')))):
            return self.child.to_representation(value)
        else:
            self.fail('type_error', input_type=type(value))

    def to_internal_value(self, data):
        if isinstance(data, (list, tuple)):
            return super(SocialMapField, self).to_internal_value(data)
        elif data in fields.NullBooleanField.TRUE_VALUES:
            return True
        elif data in fields.NullBooleanField.FALSE_VALUES:
            return False
        elif data in fields.NullBooleanField.NULL_VALUES:
            return None
        elif isinstance(data, basestring):
            return self.child.run_validation(data)
        else:
            self.fail('type_error', input_type=type(data))


class SocialSingleOrganizationMapField(BaseDictWithChildField):

    default_error_messages = {
        'invalid_keys': _('Invalid key(s) for organization map: {invalid_keys}.'),
    }
    child_fields = {
        'admins': SocialMapField(allow_null=True, required=False),
        'users': SocialMapField(allow_null=True, required=False),
        'remove_admins': fields.BooleanField(required=False),
        'remove_users': fields.BooleanField(required=False),
    }


class SocialOrganizationMapField(fields.DictField):

    child = SocialSingleOrganizationMapField()


class SocialSingleTeamMapField(BaseDictWithChildField):

    default_error_messages = {
        'missing_keys': _('Missing required key for team map: {missing_keys}.'),
        'invalid_keys': _('Invalid key(s) for team map: {invalid_keys}.'),
    }
    child_fields = {
        'organization': fields.CharField(),
        'users': SocialMapField(allow_null=True, required=False),
        'remove': fields.BooleanField(required=False),
    }


class SocialTeamMapField(fields.DictField):

    child = SocialSingleTeamMapField()


class SAMLOrgInfoValueField(BaseDictWithChildField):

    default_error_messages = {
        'missing_keys': _('Missing required key(s) for org info record: {missing_keys}.'),
    }
    child_fields = {
        'name': fields.CharField(),
        'displayname': fields.CharField(),
        'url': fields.URLField(),
    }
    allow_unknown_keys = True


class SAMLOrgInfoField(fields.DictField):

    default_error_messages = {
        'invalid_lang_code': _('Invalid language code(s) for org info: {invalid_lang_codes}.'),
    }
    child = SAMLOrgInfoValueField()

    def to_internal_value(self, data):
        data = super(SAMLOrgInfoField, self).to_internal_value(data)
        invalid_keys = set()
        for key in data.keys():
            if not re.match(r'^[a-z]{2}(?:-[a-z]{2})??$', key, re.I):
                invalid_keys.add(key)
        if invalid_keys:
            keys_display = json.dumps(list(invalid_keys)).lstrip('[').rstrip(']')
            self.fail('invalid_lang_code', invalid_lang_codes=keys_display)
        return data


class SAMLContactField(BaseDictWithChildField):

    default_error_messages = {
        'missing_keys': _('Missing required key(s) for contact: {missing_keys}.'),
    }
    child_fields = {
        'givenName': fields.CharField(),
        'emailAddress': fields.EmailField(),
    }
    allow_unknown_keys = True


class SAMLIdPField(BaseDictWithChildField):

    default_error_messages = {
        'missing_keys': _('Missing required key(s) for IdP: {missing_keys}.'),
    }
    child_fields = {
        'entity_id': fields.CharField(),
        'url': fields.URLField(),
        'x509cert': fields.CharField(validators=[validate_certificate]),
        'attr_user_permanent_id': fields.CharField(required=False),
        'attr_first_name': fields.CharField(required=False),
        'attr_last_name': fields.CharField(required=False),
        'attr_username': fields.CharField(required=False),
        'attr_email': fields.CharField(required=False),
    }
    allow_unknown_keys = True


class SAMLEnabledIdPsField(fields.DictField):

    child = SAMLIdPField()
