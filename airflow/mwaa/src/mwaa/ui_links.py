# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Links back to the Datadog UI's Configure Airflow flow, printed at the end of `scan` and `apply`."""

import urllib.parse
from typing import Optional


def app_url(dd_site: str) -> str:
    """The Datadog web app's base URL for a site.

    Bare sites (datadoghq.com, datadoghq.eu, ddog-gov.com, datad0g.com) serve
    the app from `app.<site>`; sites that already carry a subdomain
    (us3.datadoghq.com, ap1.datadoghq.com, us2.ddog-gov.com, ...) serve it
    from the site itself.
    """
    return f"https://{dd_site}" if dd_site.count(".") > 1 else f"https://app.{dd_site}"


def configure_airflow_url(dd_site: str, session_id: str, environment_name: Optional[str] = None) -> str:
    """The Configure Airflow page for a session; with an environment, its Run a DAG step."""
    query = {"session_id": session_id}
    if environment_name is not None:
        query |= {"step": "run-a-dag", "env": environment_name}
    return f"{app_url(dd_site)}/data-obs/configure/airflow?{urllib.parse.urlencode(query, quote_via=urllib.parse.quote)}"
