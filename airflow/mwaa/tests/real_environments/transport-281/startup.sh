#!/bin/sh
export MY_TEAM_SETTING=keep-me
export AIRFLOW__OPENLINEAGE__TRANSPORT='{"type": "http", "url": "https://data-obs-intake.datadoghq.com", "auth": {"type": "api_key", "apiKey": "not-a-real-key"}}'
export OPENLINEAGE_URL=https://data-obs-intake.datadoghq.com
