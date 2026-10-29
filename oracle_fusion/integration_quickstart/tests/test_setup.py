# Copyright 2026 Datadog, Inc. Licensed under the Apache-2 License.
import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('fusion_setup', Path(__file__).parents[1] / 'setup.py')
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


def args(*extra):
    return s.parse_args(['--identity-domain-url', 'https://id.example:443/',
                         '--epm-app-id', 'epm', '--epm-base-url', 'https://epm.example/', *extra])


class FakeExternal:
    def __init__(self, account=None, existing=False):
        self.env = {'DD_API_KEY': 'api-secret', 'DD_APP_KEY': 'app-secret'}
        self.calls = []
        self.account = account
        self.existing = existing
        self.user_lookups = 0

    def authenticate(self):
        self.calls.append(('authenticate',))

    def oci(self, group, action, endpoint='', **options):
        self.calls.append((group, action, options))
        if group == 'apps':
            if options['filter'].startswith('id eq'):
                return {'data': {'resources': [{'display-name': 'SaaS', 'audience': 'urn:opc:resource:faaas:fa:SYS'}]}}
            return {'data': {'resources': [{'name': 'client', 'ocid': 'app-ocid', 'allowed-scopes': []}] if self.existing else []}}
        if group == 'app':
            return {'data': {'name': 'client', 'ocid': 'app-ocid', 'client-secret': 'rotated-secret'}}
        if group == 'users':
            self.user_lookups += 1
            return {'data': {'resources': [{'id': 'iam-user'}] if self.existing or self.user_lookups > 1 else []}}
        if group == 'user':
            return {'data': {'id': 'iam-user'}}
        if group == 'app-roles':
            return {'data': {'resources': [{'id': 'admin-role', 'app': {'value': 'epm'}, 'display-name': 'Service Administrator'}]}}
        if group == 'grants':
            return {'data': {'resources': [{'id': 'grant'}] if self.existing else []}}
        if group == 'o-auth-partner-certificates':
            return {'data': {'resources': [{'id': 'old-cert'}] if self.existing else []}}
        return {}

    def http(self, method, url, headers=None, body=None, **kwargs):
        self.calls.append((method, url, body))
        if url.endswith(s.ACCOUNTS) and method == 'GET':
            return {'data': [self.account] if self.account else []}
        if '/Roles?' in url:
            return {'Resources': [{'id': 'fusion-role'}]}
        if '/Users?' in url:
            return {'Resources': [{'id': 'fusion-user'}] if self.existing else []}
        if url.endswith('/Users') and method == 'POST':
            return {'id': 'fusion-user'}
        return {}

    def prompt(self, message):
        return ''

    def sleep(self, seconds):
        self.calls.append(('sleep', seconds))

    def signing_key(self, alias):
        return 'private-key', 'certificate'


def existing_account(fusion=True):
    settings = {'client_id': 'client', 'token_url': 'https://id.example/oauth2/v1/token',
                'epm_base_url': 'https://epm.example', 'epm_application_id': 'epm'}
    if fusion:
        settings.update(fusion_base_url='https://fusion.example', fusion_application_id='fusion', oauth_scope='old-scope')
    return {'id': 'dd-id', 'attributes': {'name': 'existing', 'settings': settings}}


class SetupTests(unittest.TestCase):
    def test_validation(self):
        s.validate_args(args())
        for argv in ([], ['--fix'], ['--account-name', 'x'],
                     ['--fix', '--account-name', 'x', '--epm-app-id', 'epm']):
            with self.subTest(argv=argv), self.assertRaises(s.SetupError):
                s.validate_args(s.parse_args(argv))
        self.assertEqual(args().identity_domain_url, 'https://id.example')

    def test_invalid_url_fails_before_external_calls(self):
        io = FakeExternal()
        a = args()
        a.epm_base_url = 'http://epm.example'
        with self.assertRaises(s.SetupError):
            s.Onboarding(a, io).run()
        self.assertEqual(io.calls, [])

    def test_user_propagation_retries_are_bounded(self):
        io = FakeExternal()
        original = io.oci

        def invisible(group, action, endpoint='', **options):
            if group == 'users':
                return {'data': {'resources': []}}
            return original(group, action, endpoint, **options)

        io.oci = invisible
        with self.assertRaisesRegex(s.SetupError, 'not yet visible'):
            s.Onboarding(args(), io).run()
        self.assertEqual(sum(c[0] == 'sleep' for c in io.calls), 4)
        self.assertFalse(any(c[:2] == ('grant', 'create') for c in io.calls))

    def test_auth_prefers_api_key(self):
        io = s.External()
        with patch.object(io, 'command', return_value=b'{}') as command, patch.object(io, 'prompt') as prompt:
            io.authenticate()
        self.assertEqual(command.call_count, 1)
        prompt.assert_not_called()

    def test_auth_reuses_and_refreshes_only_owned_profile(self):
        for expired in (False, True):
            io = s.External()
            io.env = {}
            calls = []

            def command(argv, calls=calls, expired=expired, **kwargs):
                calls.append(argv)
                if argv[1] == 'iam' and len(calls) == 1:
                    raise s.SetupError('API key unavailable')
                if expired and argv[1:3] == ['session', 'validate'] and len(calls) == 2:
                    raise s.SetupError('expired')
                return b'{}'

            def config_read(cfg, path):
                cfg.read_dict({s.PROFILE: {'security_token_file': 'token'}, 'unrelated': {'security_token_file': 'other'}})

            with patch.object(io, 'command', side_effect=command), patch.object(s.configparser.ConfigParser, 'read', config_read), patch.object(io, 'prompt') as prompt:
                io.authenticate()
            prompt.assert_not_called()
            self.assertEqual(io.env['OCI_CLI_PROFILE'], s.PROFILE)
            self.assertEqual(any(c[1:3] == ['session', 'refresh'] for c in calls), expired)

    def test_auth_decline(self):
        io = s.External()
        with patch.object(io, 'command', side_effect=s.SetupError('no credentials')), patch.object(s.configparser.ConfigParser, 'read'), patch.object(io, 'prompt', return_value='n'), self.assertRaises(s.SetupError):
            io.authenticate()

    def test_scope(self):
        for audience, expected in [('', s.CONSUMER_SCOPE), ('prefix', 'prefix' + s.CONSUMER_SCOPE),
                                   (s.CONSUMER_SCOPE, s.CONSUMER_SCOPE)]:
            self.assertEqual(s.derive_scope({'audience': audience}), expected)

    def test_password_policy(self):
        for style in ({'minLength': 30, 'maxLength': 40, 'minNumerals': 5},
                      {'min-length': 30, 'max-length': 40, 'min-numerals': 5}):
            password = s.password_for_policy([style])
            self.assertGreaterEqual(len(password), 30)
            self.assertGreaterEqual(sum(c.isdigit() for c in password), 5)
            self.assertTrue(any(c.islower() for c in password))
            self.assertTrue(any(c.isupper() for c in password))
        with self.assertRaises(s.SetupError):
            s.password_for_policy([{'minLength': 30, 'maxLength': 10}])

    def test_payload_omits_empty_secrets(self):
        a = args()
        a.fusion_scope = a.epm_scope = ''
        payload = s.account_payload(a, 'client', 'token', {})['data']['attributes']
        self.assertNotIn('secrets', payload)
        self.assertNotIn('fusion_base_url', payload['settings'])
        self.assertEqual(payload['settings']['logs_config']['enabled_services'], ['epm_jobs', 'epm_audit'])

    def test_fresh_epm(self):
        io = FakeExternal()
        s.Onboarding(args('--user-email', 'a"b@example.com'), io).run()
        self.assertTrue(any(c[:2] == ('user', 'create') for c in io.calls))
        self.assertTrue(any(c[:2] == ('grant', 'create') for c in io.calls))
        payload = io.calls[-1][2]['data']['attributes']
        self.assertEqual(payload['name'], 'epm.example')
        self.assertEqual(payload['secrets']['epm_jwt_private_key'], 'private-key')

    def test_fresh_fusion_and_combined(self):
        for epm in (False, True):
            a = args('--fusion-app-id', 'fusion', '--fusion-base-url', 'https://fusion.example',
                     '--fusion-admin-username', 'admin', '--fusion-admin-password', 'password')
            if not epm:
                a.epm_app_id = a.epm_base_url = ''
            io = FakeExternal()
            s.Onboarding(a, io).run()
            self.assertTrue(any(c[0] == 'POST' and c[1].endswith('/Users') for c in io.calls))
            self.assertTrue(any(c[0] == 'PATCH' and '/Roles/fusion-role' in c[1] for c in io.calls))
            self.assertEqual('epm_token' in io.calls[-1][2]['data']['attributes']['secrets'], epm)

    def test_add_epm_preserves_fusion(self):
        io = FakeExternal(existing_account(), existing=True)
        a = s.parse_args(['--account-name', 'existing', '--fusion-app-id', 'fusion', '--epm-app-id', 'epm'])
        s.Onboarding(a, io).run()
        self.assertFalse(any('/hcmRestApi/' in str(c) for c in io.calls))
        self.assertFalse(any(c[:2] == ('grant', 'create') for c in io.calls))
        payload = io.calls[-1][2]['data']['attributes']
        self.assertEqual(payload['settings']['fusion_base_url'], 'https://fusion.example')
        self.assertEqual(io.calls[-1][0], 'PATCH')
        self.assertEqual(payload['secrets']['client_secret'], 'rotated-secret')

    def test_repair_both_products_and_epm_only(self):
        for fusion in (True, False):
            io = FakeExternal(existing_account(fusion), existing=True)
            a = s.parse_args(['--account-name', 'existing', '--fix', '--fusion-admin-username', 'admin',
                              '--fusion-admin-password', 'password'])
            s.Onboarding(a, io).run()
            patches = [c for c in io.calls if c[:2] == ('app', 'patch')]
            self.assertEqual(len(patches), 2)  # desired state plus secret rotation
            self.assertTrue(any(c[:2] == ('o-auth-partner-certificate', 'delete') for c in io.calls))

    def test_deleted_app_fails_before_writes(self):
        io = FakeExternal(existing_account(False), existing=False)
        with self.assertRaisesRegex(s.SetupError, 'deleted'):
            s.Onboarding(s.parse_args(['--account-name', 'existing', '--fix']), io).run()
        self.assertFalse(any(c[1] in ('create', 'patch', 'put', 'delete') for c in io.calls if len(c) > 1))

    def test_command_failure_redacts_secret_arguments(self):
        with patch.object(s.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, b'', b'secret')), self.assertRaises(s.SetupError) as error:
            s.External().command(['oci', 'identity-domains', '--password', 'secret'])
        self.assertNotIn('secret', str(error.exception))

    def test_signing_key_works_without_disk_files(self):
        key, cert = s.External().signing_key('test-alias')
        self.assertIn('PRIVATE KEY', key)
        self.assertTrue(cert)


if __name__ == '__main__':
    unittest.main()
