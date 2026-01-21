import subprocess
import sys

AZ_VERS_TIMEOUT = 5  # seconds


def get_az_and_python_version(timeout: int = AZ_VERS_TIMEOUT) -> str:
    """
    Return the az and python versions on success, otherwise return a failure string.
    """
    python_version = sys.version_info
    python_result = f"python version: {python_version[0]}.{python_version[1]}.{python_version[2]}"
    try:
        res = subprocess.run(
            ["az", "version", "--output", "json"],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        az_result = f"az version:\n{res.stdout.strip()}"
    except subprocess.TimeoutExpired:
        az_result = f"Could not retrieve 'az version': timeout after {timeout}s"
    except Exception as e:
        az_result = f"Could not retrieve 'az version': {e}"
    return f"\n{az_result}\n{python_result}"
