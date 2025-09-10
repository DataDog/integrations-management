#!/usr/bin/env python3
"""
Setup.py for azure-logging-install package.

This file enables editable installs (pip install -e .) while the main
configuration remains in pyproject.toml for modern Python packaging.
"""

from setuptools import setup, find_packages

setup(
    name="azure-logging-install",
    version="0.1.0",
    description="Azure Log Forwarding Orchestration Installation",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.5",
    extras_require={
        "dev": ["pytest==6.1.2"],
    },
    entry_points={
        "console_scripts": [
            "azure-logging-install=azure_logging_install.main:main",
        ],
    },
)
