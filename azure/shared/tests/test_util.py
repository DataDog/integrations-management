import sys
from subprocess import TimeoutExpired
from unittest import TestCase
from unittest.mock import Mock
from unittest.mock import patch as mock_patch

from az_shared.util import AZ_VERS_TIMEOUT, get_az_and_python_version


class TestGetAzAndPythonVersion(TestCase):
    def patch(self, path: str, **kwargs):
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_get_az_and_python_version_success(self):
        """Test az and python versions return on success."""
        subprocess_mock = self.patch("az_shared.util.subprocess.run")
        result = Mock()
        result.returncode = 0
        result.stdout = '{"azure-cli": "2.0.0"}\n'
        result.stderr = ""
        subprocess_mock.return_value = result
        result = get_az_and_python_version()
        self.assertIn('\naz version:\n{"azure-cli": "2.0.0"}', result)
        self.assertRegex(result, r"\npython version: \d+\.\d+\.\d+")
        subprocess_mock.assert_called_once_with(
            ["az", "version", "--output", "json"],
            check=True,
            capture_output=True,
            text=True,
            timeout=AZ_VERS_TIMEOUT,
        )

    def test_get_az_and_python_version_timeout(self):
        """Test az version returns a message on timeout."""
        subprocess_mock = self.patch("az_shared.util.subprocess.run")
        subprocess_mock.side_effect = TimeoutExpired(cmd="az version", timeout=AZ_VERS_TIMEOUT)
        self.assertEqual(
            get_az_and_python_version(), "\nCould not retrieve 'az version': timeout after 5s\npython version: 3.9.22"
        )
        subprocess_mock.assert_called_once_with(
            ["az", "version", "--output", "json"],
            check=True,
            capture_output=True,
            text=True,
            timeout=AZ_VERS_TIMEOUT,
        )

    def test_get_az_and_python_version_exception(self):
        """Test az version returns a message on unexpected exceptions and that python version is still returned."""
        subprocess_mock = self.patch("az_shared.util.subprocess.run")
        subprocess_mock.side_effect = ValueError("bad")
        self.assertEqual(get_az_and_python_version(), "\nCould not retrieve 'az version': bad\npython version: 3.9.22")
        subprocess_mock.assert_called_once_with(
            ["az", "version", "--output", "json"],
            check=True,
            capture_output=True,
            text=True,
            timeout=AZ_VERS_TIMEOUT,
        )
