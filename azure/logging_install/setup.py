#!/usr/bin/env python3
"""
Reads configuration from pyproject.toml and sets up project accordingly. setup.py is needed for Python 3.5 compatibility.
"""

from setuptools import setup, find_packages
import toml

with open("pyproject.toml", "r") as f:
    pyproject_data = toml.load(f)

project_config = pyproject_data.get("project", {})

setup(
    name=project_config.get("name"),
    version=project_config.get("version"),
    description=project_config.get("description", "Azure Log Forwarding Orchestration Installation"),
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=project_config.get("requires-python"),
    install_requires=project_config.get("dependencies", []),
    extras_require=project_config.get("optional-dependencies", {}),
    entry_points={
        "console_scripts": [
            "azure-logging-install=azure_logging_install.main:main",
        ],
    },
)
