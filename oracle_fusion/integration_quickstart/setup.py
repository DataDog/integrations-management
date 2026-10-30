#!/usr/bin/env python3
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# Copyright 2026 Datadog, Inc.
"""Oracle Fusion / EPM onboarding. Requires Python 3.6+, OCI CLI and OpenSSL."""

import argparse
import base64
import configparser
import json
import os
import secrets
import shutil
import string
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

ACCOUNTS = '/api/v2/web-integrations/oracle-fusion/accounts'
PATCH_SCHEMA = 'urn:ietf:params:scim:api:messages:2.0:PatchOp'
IDCS_SCHEMA = 'urn:ietf:params:scim:schemas:oracle:idcs:'
CONSUMER_SCOPE = 'urn:opc:resource:consumer::all'
PROFILE = 'datadog-fusion'
APP_NAME = 'Datadog Fusion Integration'
FIELDS = {
    'fusion_base_url': 'fusion_base_url', 'epm_base_url': 'epm_base_url',
    'fusion_app_id': 'fusion_application_id', 'epm_app_id': 'epm_application_id',
    'fusion_scope': 'oauth_scope', 'epm_scope': 'epm_oauth_scope',
}


class SetupError(Exception):
    """An actionable onboarding failure (never includes secret-bearing responses)."""


def require(condition, message):
    """Fail with actionable guidance when an onboarding invariant is not met."""
    if not condition:
        raise SetupError(message)


def normalise_url(url):
    """Remove one trailing slash and the default HTTPS port (Python 3.6 compatible)."""
    for suffix in ('/', ':443'):
        if url.endswith(suffix):  # noqa: FURB188 -- removesuffix requires Python 3.9
            url = url[:-len(suffix)]
    return url


def parse_args(argv=None):
    """Parse the legacy shell CLI and normalize supplied service URLs."""
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('identity-domain-url', 'fusion-app-id', 'epm-app-id', 'fusion-base-url',
                 'epm-base-url', 'fusion-admin-username', 'fusion-admin-password',
                 'user-email', 'account-name'):
        parser.add_argument('--' + flag, default='')
    parser.add_argument('--fix', action='store_true', help='Repair an existing account; rotates credentials')
    args = parser.parse_args(argv)
    for field in ('identity_domain_url', 'fusion_base_url', 'epm_base_url'):
        setattr(args, field, normalise_url(getattr(args, field)))
    return args


def validate_args(a):
    """Reject incompatible flags and missing mode-specific prerequisites."""
    if a.fix:
        require(a.account_name, '--account-name is required with --fix')
        forbidden = ('identity_domain_url', 'epm_app_id', 'fusion_base_url', 'epm_base_url')
    elif a.account_name:
        forbidden = ('identity_domain_url', 'fusion_base_url', 'fusion_admin_username',
                     'fusion_admin_password', 'user_email')
        require(a.fusion_app_id and a.epm_app_id,
                'Adding EPM to an account requires --fusion-app-id and --epm-app-id')
    else:
        forbidden = ()
        require(a.identity_domain_url, '--identity-domain-url is required')
        require(a.fusion_app_id or a.epm_app_id, 'Provide --fusion-app-id or --epm-app-id')
        if a.fusion_app_id:
            require(a.fusion_base_url and a.fusion_admin_username and a.fusion_admin_password,
                    'Fusion requires --fusion-base-url, --fusion-admin-username and --fusion-admin-password')
        if a.epm_app_id:
            require(a.epm_base_url, '--epm-base-url is required for EPM')
    validate_input_urls(a)
    invalid = [f'--{f.replace("_", "-")}' for f in forbidden if getattr(a, f)]
    require(not invalid, 'Invalid flags for this mode: ' + ', '.join(invalid))


def validate_input_urls(a):
    """Accept only HTTPS origins without embedded credentials, paths or queries."""
    for field in ('identity_domain_url', 'fusion_base_url', 'epm_base_url'):
        url = getattr(a, field)
        if url:
            parsed = urlsplit(url)
            require(parsed.scheme == 'https' and parsed.hostname and not parsed.username
                    and not parsed.password and not parsed.query and not parsed.fragment
                    and parsed.path in ('', '/'),
                    f'--{field.replace("_", "-")} must be an HTTPS base URL without credentials, path or query')


def derive_scope(app):
    """Append the consumer scope exactly once to the SaaS app audience."""
    audience = app.get('audience', '')
    return audience if audience.endswith('consumer::all') else audience + CONSUMER_SCOPE


def resources(response):
    """Extract OCI CLI list resources, defaulting to an empty collection."""
    return response.get('data', {}).get('resources', [])


def first(items):
    """Return the first matching resource or an empty mapping."""
    return next(iter(items), {})


def password_for_policy(policies):
    """Generate a shuffled cryptographic token satisfying default policy minima."""
    policy = next((p for p in policies if 'default' in p.get('name', '').lower()), first(policies))

    def value(camel, kebab, default):
        return int(policy.get(camel, policy.get(kebab, default)))

    minimum = value('minLength', 'min-length', 14)
    maximum = value('maxLength', 'max-length', 20)
    groups = [(string.ascii_lowercase, value('minLowerCase', 'min-lower-case', 1)),
              (string.ascii_uppercase, value('minUpperCase', 'min-upper-case', 1)),
              (string.digits, value('minNumerals', 'min-numerals', 1)),
              ('!@#$%^*_-+=', value('minSpecialChars', 'min-special-chars', 1))]
    require(all(n >= 0 for _, n in groups) and maximum >= max(minimum, sum(n for _, n in groups), 1),
            'Identity domain password policy has inconsistent length requirements')
    length = max(minimum, min(24, maximum), sum(n for _, n in groups))
    chars = [secrets.choice(pool) for pool, n in groups for _ in range(n)]
    pool = ''.join(pool for pool, n in groups if n or pool != groups[-1][0])
    chars.extend(secrets.choice(pool) for _ in range(length - len(chars)))
    secrets.SystemRandom().shuffle(chars)
    return ''.join(chars)


def account_payload(a, client_id, token_url, credentials):
    """Construct a Datadog account payload, omitting absent settings and secrets."""
    settings = {'client_id': client_id, 'token_url': token_url, 'version': '1.1'}
    settings.update({key: getattr(a, field) for field, key in FIELDS.items() if getattr(a, field, '')})
    enabled = (['ess', 'audit'] if a.fusion_base_url else []) + (['epm_jobs', 'epm_audit'] if a.epm_base_url else [])
    if enabled:
        settings['logs_config'] = {'enabled_services': enabled}
    attrs = {'name': a.account_name, 'settings': settings}
    if any(credentials.values()):
        attrs['secrets'] = {k: v for k, v in credentials.items() if v}
    return {'data': {'type': 'Account', 'attributes': attrs}}


class NoRedirect(HTTPRedirectHandler):
    """Prevent credential forwarding across service redirects."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Decline redirects; signature follows urllib's handler interface."""
        return  # Do not forward credentials to a redirected host.


class External:
    """All effects live here so orchestration can be tested without a cloud account."""

    def __init__(self):
        self.env = os.environ.copy()
        self.opener = build_opener(NoRedirect())

    def command(self, args, *, input=None, interactive=False):
        """Run a process without exposing secret arguments or output on failure."""
        result = subprocess.run(args, input=input, stdout=None if interactive else subprocess.PIPE,
                                stderr=None if interactive else subprocess.PIPE, env=self.env, check=False)
        require(result.returncode == 0, f'{args[0]} {args[1]} failed. Check credentials and administrator permissions, then rerun.')
        return result.stdout or b''

    def oci(self, group, action, endpoint='', **options):
        """Serialize structured OCI arguments without shell interpolation."""
        args = ['oci', 'identity-domains', group, action]
        if endpoint:
            options['endpoint'] = endpoint
        options['output'] = 'json'
        for key, value in options.items():
            args.append('--' + key.replace('_', '-'))
            if value is not None:
                args.append(json.dumps(value) if isinstance(value, (list, dict, bool)) else str(value))
        raw = self.command(args)
        return json.loads(raw) if raw.strip() else {}

    def http(self, method, url, headers=None, body=None, auth=None, allowed=(200, 201, 204)):
        """Issue a bounded request, rejecting unexpected statuses without dumping secrets."""
        headers = dict(headers or {})
        if auth:
            headers['Authorization'] = 'Basic ' + base64.b64encode((':'.join(auth)).encode()).decode()
        headers['Accept'] = 'application/json'
        if body is not None:
            headers['Content-Type'] = 'application/json'
        request = Request(url, data=json.dumps(body).encode() if body is not None else None,
                          headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=60) as response:
                status, raw = response.status, response.read()
        except HTTPError as error:
            status, raw = error.code, error.read()
        except URLError:
            raise SetupError('Cannot reach service. Check the configured URL and connectivity.') from None
        require(status in allowed, f'{method} {urlsplit(url).path} failed (HTTP {status}). Check permissions and rerun.')
        return json.loads(raw) if raw.strip() and status in (200, 201) else {}

    def prompt(self, message):
        """Prompt interactively, treating closed input as a declined choice."""
        try:
            return input(message)
        except EOFError:
            return ''

    def sleep(self, seconds):
        """Delay between bounded IAM propagation attempts."""
        time.sleep(seconds)

    def authenticate(self):
        """Prefer API keys, then reuse our own session, then offer browser login."""
        def works(args):
            try:
                self.command(['oci'] + args)
                return True
            except SetupError:
                return False

        if works(['iam', 'region', 'list', '--output', 'json']):
            return
        cfg = configparser.ConfigParser()
        cfg.read(self.env.get('OCI_CONFIG_FILE', os.path.expanduser('~/.oci/config')))
        session = ['--profile', PROFILE, '--auth', 'security_token']
        if cfg.has_section(PROFILE) and cfg.get(PROFILE, 'security_token_file', fallback=''):
            self.env.update(OCI_CLI_PROFILE=PROFILE, OCI_CLI_AUTH='security_token')
            if works(['session', 'validate'] + session) or (
                    works(['session', 'refresh'] + session) and works(['session', 'validate'] + session)):
                require(works(['iam', 'region', 'list']), 'OCI session lacks tenancy permissions')
                return
        require(self.prompt('Use browser-based OCI authentication? [y/N] ').lower() in ('y', 'yes'),
                'Configure OCI CLI credentials with oci setup config, or choose browser authentication')
        region = self.prompt('OCI region [us-ashburn-1]: ') or 'us-ashburn-1'
        tenancy = self.prompt('OCI tenancy name: ')
        require(tenancy, 'Tenancy name is required')
        self.command(['oci', 'session', 'authenticate', '--profile-name', PROFILE,
                      '--region', region, '--tenancy-name', tenancy], interactive=True)
        self.env.update(OCI_CLI_PROFILE=PROFILE, OCI_CLI_AUTH='security_token')
        require(works(['iam', 'region', 'list']), 'OCI session lacks tenancy permissions')

    def signing_key(self, alias):
        """Generate a private key and DER certificate through pipes, never files."""
        key = self.command(['openssl', 'genrsa', '2048'])
        cert = self.command(['openssl', 'req', '-x509', '-key', '/dev/stdin', '-days', '3650',
                             '-subj', '/CN=' + alias, '-outform', 'DER'], input=key)
        return key.decode(), base64.b64encode(cert).decode()


class Onboarding:
    """Reconcile Oracle resources in ordered, independently testable phases."""
    def __init__(self, args, external):
        self.a, self.io = args, external
        self.credentials = {}
        self.client_id = ''
        self.token_url = ''

    def dd(self, method, path, body=None):
        """Call the selected Datadog site using the supplied API credentials."""
        env = self.io.env
        return self.io.http(method, 'https://api.' + env.get('DD_SITE', 'datadoghq.com') + path,
                            {'DD-API-KEY': env['DD_API_KEY'], 'DD-APPLICATION-KEY': env['DD_APP_KEY']}, body)

    def oci(self, group, action, **options):
        """Call OCI in the resolved identity domain."""
        return self.io.oci(group, action, self.a.identity_domain_url, **options)

    def lookup(self, group, filter):
        """List resources matching a SCIM filter in this domain."""
        return resources(self.oci(group, 'list', filter=filter))

    def fusion(self, method, resource, body=None, **kwargs):
        """Call Fusion SCIM using transient admin credentials."""
        return self.io.http(method, self.a.fusion_base_url + '/hcmRestApi/scim/' + resource,
                            body=body, auth=(self.a.fusion_admin_username, self.a.fusion_admin_password), **kwargs)

    def backfill(self, account):
        """Preserve stored product settings that were not supplied on this run."""
        a = self.a
        settings = account.get('attributes', {}).get('settings', {})
        for field, key in FIELDS.items():
            if not getattr(a, field, ''):
                setattr(a, field, settings.get(key, ''))
        return settings

    def run(self):
        """Validate first, reconcile apps/users/grants, rotate credentials, then register."""
        a = self.a
        validate_args(a)
        require(self.io.env.get('DD_API_KEY') and self.io.env.get('DD_APP_KEY'), 'DD_API_KEY and DD_APP_KEY are required')
        accounts = self.dd('GET', ACCOUNTS).get('data', [])
        account = first(x for x in accounts if x.get('attributes', {}).get('name') == a.account_name)
        already_fusion = False
        a.fusion_scope = a.epm_scope = ''
        if a.account_name:
            already_fusion = self.load_account(account)
        self.token_url = self.token_url or a.identity_domain_url + '/oauth2/v1/token'
        self.validate_service_urls()
        self.io.authenticate()
        self.resolve_scopes()
        provision_fusion = a.fusion_app_id and (not already_fusion or a.fix)
        role_id = self.check_services(provision_fusion)
        app_id, reused = self.ensure_application()
        self.ensure_user(provision_fusion, role_id)
        user_id = self.grant_epm_access() if a.epm_app_id else ''
        account = self.registration_target(accounts, account)
        self.ensure_client_secret(app_id, reused)
        if a.epm_app_id:
            self.rotate_epm_credentials(user_id)
        self.register_account(account)
        self.print_summary()

    def load_account(self, account):
        """Resolve stored settings and check mode-specific requirements before writes."""
        a = self.a
        if a.account_name:
            require(account, f'No Datadog account named {a.account_name!r} found')
            settings = self.backfill(account)
            self.client_id = settings.get('client_id', '')
            require(self.client_id, 'Account has no client ID')
            self.token_url = settings.get('token_url', '')
            parsed = urlsplit(self.token_url)
            require(parsed.scheme == 'https' and parsed.netloc, 'Account token URL must be HTTPS')
            a.identity_domain_url = normalise_url(f'{parsed.scheme}://{parsed.netloc}')
            already_fusion = bool(settings.get('fusion_base_url'))
            if a.fix and already_fusion:
                require(a.fusion_app_id and a.fusion_admin_username and a.fusion_admin_password,
                        'Fusion repair requires a Fusion app ID and Fusion admin credentials')
            if not a.fix:
                require(already_fusion, 'Adding EPM requires an existing Fusion integration')
            require(not a.epm_app_id or a.epm_base_url, '--epm-base-url is required')
        return already_fusion

    def validate_service_urls(self):
        """Reject unsafe stored URLs before sending admin credentials."""
        a = self.a
        # Stored URLs are also untrusted inputs; validate them before sending admin credentials.
        for url in (a.identity_domain_url, a.fusion_base_url, a.epm_base_url):
            if url:
                parsed = urlsplit(url)
                require(parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password,
                        'Stored service URLs must use HTTPS without embedded credentials')

    def resolve_scopes(self):
        """Resolve enabled product scopes, including the legacy Fusion audience prompt."""
        a = self.a
        for product in ('fusion', 'epm'):
            app_id = getattr(a, product + '_app_id')
            if not app_id:
                continue
            app = first(self.lookup('apps', 'id eq ' + json.dumps(app_id)))
            require(app.get('display-name'), f'{product} app ID not found; verify identity domain and administrator access')
            scope = derive_scope(app)
            if product == 'fusion':
                scope = self.confirm_fusion_scope(scope)
            setattr(a, product + '_scope', scope)

    def confirm_fusion_scope(self, scope):
        """Offer an explicit System Name override for legacy Fusion audiences."""
        if scope.startswith('urn:opc:resource:faaas:fa:'):
            return scope
        print('Unexpected Fusion audience. Find System Name in OCI Console → Fusion Applications → Environments.')
        if self.io.prompt('Continue derived scope [1] or supply System Name [2]? ') != '2':
            return scope
        system = self.io.prompt('Fusion instance System Name (case sensitive): ')
        return 'urn:opc:resource:faaas:fa:' + system + CONSUMER_SCOPE if system else scope

    def check_services(self, provision_fusion):
        """Validate connectivity and return the manually configured Fusion role ID."""
        a = self.a
        role_id = ''
        if provision_fusion:
            self.fusion('GET', 'Users?count=1')
            roles = self.fusion('GET', 'Roles?' + urlencode({'filter': 'name eq "DD_INTEGRATION_ROLE"'}))
            role_id = first(roles.get('Resources', [])).get('id')
            require(role_id, 'Create DD_INTEGRATION_ROLE in Fusion Security Console and mark it Requestable in Manage Role Provisioning Rules; see README.md')
        if a.epm_app_id:
            self.io.http('GET', a.epm_base_url + '/HyperionPlanning/rest/v3/applications', allowed=range(200, 600))
        return role_id

    def ensure_application(self):
        """Create or reconcile the confidential app; return its OCID and reuse status."""
        a = self.a
        app_filter = ('name eq ' + json.dumps(self.client_id)) if a.account_name else ('displayName eq ' + json.dumps(APP_NAME))
        app = first(self.lookup('apps', app_filter))
        require(not a.account_name or app, 'Confidential app was deleted; remove the Datadog account and reinstall from scratch')
        scopes = [{'fqs': s} for s in (a.fusion_scope, a.epm_scope) if s]
        desired = {'allowedScopes': scopes, 'isOAuthClient': True,
                   'allowedGrants': ['client_credentials', 'urn:ietf:params:oauth:grant-type:jwt-bearer'],
                   'clientType': 'confidential', 'clientIPChecking': 'anywhere', 'bypassConsent': True, 'active': True}
        if app:
            self.client_id = app.get('name', '')
            app_id = app.get('ocid', '')
            require(self.client_id and app_id, 'Existing confidential app has no name or OCID')
            present = {s.get('fqs') for s in app.get('allowed-scopes', [])}
            if a.fix or any(s['fqs'] not in present for s in scopes):
                self.oci('app', 'patch', app_id=app_id, schemas=[PATCH_SCHEMA],
                         operations=[{'op': 'replace', 'path': k, 'value': v} for k, v in desired.items()])
        else:
            app_id = self.create_application(scopes, desired['allowedGrants'])
        return app_id, bool(app)

    def create_application(self, scopes, grants):
        """Create a confidential app and retrieve its initial secret before proceeding."""
        result = self.oci('app', 'create', schemas=[IDCS_SCHEMA + 'App'], display_name=APP_NAME,
                          description='Datadog integration for Oracle Fusion and Fusion EPM monitoring',
                          based_on_template={'value': 'CustomWebAppTemplateId', 'wellKnownId': 'CustomWebAppTemplateId'},
                          is_o_auth_client=True, allowed_grants=grants, client_type='confidential',
                          client_ip_checking='anywhere', bypass_consent=True, active=True, allowed_scopes=scopes)['data']
        self.client_id, app_id = result.get('name', ''), result.get('ocid', '')
        self.credentials['client_secret'] = result.get('client-secret', '')
        require(self.client_id and app_id, 'Created app response has no client ID or OCID')
        if not self.credentials['client_secret']:
            self.credentials['client_secret'] = self.oci('app', 'get', app_id=app_id).get('data', {}).get('client-secret', '')
        return app_id

    def ensure_user(self, provision_fusion, role_id):
        """Create the integration user in Fusion or IAM and assert the Fusion role."""
        a = self.a
        user = {'userName': self.client_id, 'name': {'familyName': 'Datadog Integration'}, 'active': True}
        if a.user_email:
            user['emails'] = [{'value': a.user_email, 'type': 'work', 'primary': True}]
        user_filter = 'userName eq ' + json.dumps(self.client_id)
        if provision_fusion:
            existing = self.fusion('GET', 'Users?' + urlencode({'filter': user_filter}))
            fusion_user = first(existing.get('Resources', []))
            if not fusion_user:
                fusion_user = self.fusion('POST', 'Users', dict(user, schemas=['urn:scim:schemas:core:2.0:User']), allowed=(201,))
            require(fusion_user.get('id'), 'Fusion user response has no ID')
            self.fusion('PATCH', 'Roles/' + quote(role_id, safe=''),
                        {'schemas': ['urn:oracle:apps:scim:schemas:fa:1.0:Role'],
                         'members': [{'value': fusion_user['id'], 'operation': 'ADD'}]}, allowed=(200, 204))
        elif not a.fusion_app_id and a.epm_app_id:
            iam_user = first(self.lookup('users', user_filter))
            if not iam_user:
                options = {'schemas': ['urn:ietf:params:scim:schemas:core:2.0:User'],
                           'user_name': self.client_id, 'name': user['name'], 'active': True}
                if a.user_email:
                    options['emails'] = user['emails']
                iam_user = self.oci('user', 'create', **options).get('data', {})
            require(iam_user.get('id'), 'OCI user response has no ID')

    def wait_for_iam_user(self):
        """Wait at most four intervals for Fusion-to-IAM user propagation."""
        user_filter = 'userName eq ' + json.dumps(self.client_id)
        for attempt in range(5):
            user_id = first(self.lookup('users', user_filter)).get('id', '')
            if user_id:
                return user_id
            if attempt < 4:
                self.io.sleep(10)
        raise SetupError('User not yet visible in OCI IAM. Wait a few minutes and rerun.')

    def grant_epm_access(self):
        """Ensure the EPM Service Administrator grant and return the IAM user ID."""
        a = self.a
        user_id = self.wait_for_iam_user()
        roles = resources(self.oci('app-roles', 'list', filter='app.value eq ' + json.dumps(a.epm_app_id), count=200))
        role = first(r for r in roles if r.get('app', {}).get('value') == a.epm_app_id
                     and r.get('display-name', '').lower() == 'service administrator')
        require(role.get('id'), 'EPM Service Administrator role not found; check EPM app ID')
        grant_filter = (f'grantee.value eq {json.dumps(user_id)} and app.value eq {json.dumps(a.epm_app_id)} '
                        f'and entitlement.attributeValue eq {json.dumps(role["id"])}')
        if not self.lookup('grants', grant_filter):
            self.oci('grant', 'create', schemas=[IDCS_SCHEMA + 'Grant'], grant_mechanism='ADMINISTRATOR_TO_USER',
                     grantee={'type': 'User', 'value': user_id}, app={'value': a.epm_app_id},
                     entitlement={'attributeName': 'appRoles', 'attributeValue': role['id']})
        return user_id

    def registration_target(self, accounts, account):
        """Find an existing auto-named account and preserve the other product's settings."""
        a = self.a
        if not a.account_name:
            a.account_name = urlsplit(a.fusion_base_url or a.epm_base_url).hostname or 'Oracle Fusion Integration'
            account = first(x for x in accounts if x.get('attributes', {}).get('name') == a.account_name)
            if account:
                self.backfill(account)
        return account

    def ensure_client_secret(self, app_id, reused):
        """Rotate an existing app's unavailable secret before registering it."""
        if reused:
            result = self.oci('app', 'patch', app_id=app_id, schemas=[PATCH_SCHEMA],
                              operations=[{'op': 'replace', 'path': 'clientSecret', 'value': ''}])
            self.credentials['client_secret'] = result.get('data', {}).get('client-secret', '')
        require(self.credentials.get('client_secret'), 'Could not retrieve client secret; check OCI app OAuth Configuration')

    def rotate_epm_credentials(self, user_id):
        """Replace the EPM fallback password and the in-memory JWT signing key."""
        policies = resources(self.oci('password-policies', 'list'))
        self.credentials['epm_token'] = password_for_policy(policies)
        self.oci('user-password-changer', 'put', user_password_changer_id=user_id,
                 schemas=[IDCS_SCHEMA + 'UserPasswordChanger'], password=self.credentials['epm_token'], force=None)
        alias = 'datadog-fusion-jwt-' + self.client_id
        key, certificate = self.io.signing_key(alias)
        self.credentials['epm_jwt_private_key'] = key
        old_cert = first(self.lookup('o-auth-partner-certificates', 'certificateAlias eq ' + json.dumps(alias)))
        if old_cert:
            self.oci('o-auth-partner-certificate', 'delete', o_auth_partner_certificate_id=old_cert['id'], force=None)
        self.oci('o-auth-partner-certificate', 'create', schemas=[IDCS_SCHEMA + 'OAuthPartnerCertificate'],
                 certificate_alias=alias, x509_base64_certificate=certificate)

    def register_account(self, account):
        """Create or update Datadog only after provisioning and rotation succeed."""
        payload = account_payload(self.a, self.client_id, self.token_url, self.credentials)
        path = ACCOUNTS + '/' + quote(account['id'], safe='') if account else ACCOUNTS
        self.dd('PATCH' if account else 'POST', path, payload)

    def print_summary(self):
        """Report completion and remaining manual EPM steps without credentials."""
        a = self.a
        print(('Repair' if a.fix else 'Onboarding') + ' complete: ' + a.account_name)
        if a.epm_app_id:
            print('In EPM: Tools → Access Control → Role Assignment Report: verify the Datadog Integration user.')
            print('In OCI: Domains → Oracle Cloud Services → EPM → OAuth Configuration: add secondary audience ' + a.epm_base_url)


def main(argv=None):
    """Run the CLI and convert expected failures into actionable exit messages."""
    try:
        args = parse_args(argv)
        validate_args(args)
        for tool in ('oci', 'openssl'):
            require(shutil.which(tool), f'{tool} is required on PATH')
        Onboarding(args, External()).run()
        return 0
    except (SetupError, ValueError, OSError) as error:
        print(f'FAILED: {error}\nOnce resolved, rerun the script to continue.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
