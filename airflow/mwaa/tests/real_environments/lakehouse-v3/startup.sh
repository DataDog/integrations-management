#!/bin/sh
get_secret() {
    _result=$(aws secretsmanager get-secret-value --secret-id "$1" --query SecretString --output text 2>&1)
    if [ $? -ne 0 ]; then
        echo ""
    else
        echo "$_result"
    fi
}

DD_API_KEY=$(get_secret "example/dd-api-key")
OPENLINEAGE_API_KEY=$(get_secret "example/openlineage-api-key")
OPENLINEAGE_API_KEY="${OPENLINEAGE_API_KEY:-$DD_API_KEY}"
export DD_API_KEY OPENLINEAGE_API_KEY

export AIRFLOW__OPENLINEAGE__NAMESPACE=${AIRFLOW_ENV_NAME}
export OPENLINEAGE_CLIENT_LOGGING=DEBUG

export OPENLINEAGE_URL="${OPENLINEAGE_URL:-https://data-obs-intake.datad0g.com}"
export OPENLINEAGE_API_KEY="${OPENLINEAGE_API_KEY:-$DD_API_KEY}"
export SECOND_OPENLINEAGE_URL="${SECOND_OPENLINEAGE_URL:-https://data-obs-intake.datadoghq.com}"

export OPENLINEAGE__TRANSPORT__TYPE=composite
export OPENLINEAGE__TRANSPORT__CONTINUE_ON_FAILURE=true
export OPENLINEAGE__TRANSPORT__TRANSPORTS__CONSOLE__TYPE=console

# openlineage-python aliases OPENLINEAGE_URL/API_KEY to default_http.
export OPENLINEAGE__TRANSPORT__TRANSPORTS__DEFAULT_HTTP__TYPE=http
export OPENLINEAGE__TRANSPORT__TRANSPORTS__DEFAULT_HTTP__URL="${OPENLINEAGE_URL}"
export OPENLINEAGE__TRANSPORT__TRANSPORTS__DEFAULT_HTTP__AUTH__TYPE=api_key
export OPENLINEAGE__TRANSPORT__TRANSPORTS__DEFAULT_HTTP__AUTH__API_KEY="${OPENLINEAGE_API_KEY}"
export OPENLINEAGE__TRANSPORT__TRANSPORTS__DEFAULT_HTTP__COMPRESSION=gzip

export OPENLINEAGE__TRANSPORT__TRANSPORTS__SECOND__TYPE=http
export OPENLINEAGE__TRANSPORT__TRANSPORTS__SECOND__URL="${SECOND_OPENLINEAGE_URL}"
export OPENLINEAGE__TRANSPORT__TRANSPORTS__SECOND__AUTH__TYPE=api_key
export OPENLINEAGE__TRANSPORT__TRANSPORTS__SECOND__AUTH__API_KEY="${SECOND_DD_API_KEY}"

sudo tee -a /etc/example.yaml > /dev/null 2>&1 <<EOT || true
additional_endpoints:
  - ${SECOND_DD_API_KEY}
EOT
