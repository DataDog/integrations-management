#!/bin/sh
# Datadog's MWAA docs recipe, plus the two Airflow 2.7/2.8 workaround variables
export OPENLINEAGE_URL=https://data-obs-intake.datad0g.com
export OPENLINEAGE_API_KEY=$(aws secretsmanager get-secret-value --secret-id example/dd-api-key --query SecretString --output text)
export AIRFLOW__OPENLINEAGE__NAMESPACE=${AIRFLOW_ENV_NAME}
export AIRFLOW__OPENLINEAGE__CONFIG_PATH=""
export AIRFLOW__OPENLINEAGE__DISABLED_FOR_OPERATORS=""
