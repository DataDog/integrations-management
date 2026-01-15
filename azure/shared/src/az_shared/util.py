import subprocess
import sys

AZ_VERS_TIMEOUT = 5  # seconds


def get_az_and_python_version(timeout: int = AZ_VERS_TIMEOUT) -> str:
    """
    Return the az and python versions on success, otherwise return a failure string.
    """
    try:
        res = subprocess.run(
            ["az", "version", "--output", "json"],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        python_version = sys.version_info
        return f"\naz version:\n{res.stdout.strip()}\npython version: {python_version[0]}.{python_version[1]}.{python_version[2]}"
    except subprocess.TimeoutExpired:
        return f"\nCould not retrieve 'az version': timeout after {timeout}s"
    except Exception as e:
        return f"\nCould not retrieve 'az and/or python version': {e}"
