import subprocess

AZ_VERS_TIMEOUT = 5  # seconds


def get_az_version(timeout: int = AZ_VERS_TIMEOUT) -> str:
    """
    Return the az version on success, otherwise return a failure
    string starting with "Could not retrieve 'az version'".
    """
    try:
        res = subprocess.run(
            ["az", "version", "--output", "json"],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return f"\naz version:\n{res.stdout.strip()}"
    except subprocess.TimeoutExpired:
        return f"\nCould not retrieve 'az version': timeout after {timeout}s"
    except Exception as e:
        return f"\nCould not retrieve 'az version': {e}"
