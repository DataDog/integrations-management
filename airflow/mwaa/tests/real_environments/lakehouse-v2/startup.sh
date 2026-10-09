#!/bin/sh
get_secret() {
    aws secretsmanager get-secret-value --secret-id "$1" --query SecretString --output text 2>/dev/null || true
}

DD_API_KEY=$(get_secret "example/dd-api-key")
OPENLINEAGE_API_KEY=$(get_secret "example/openlineage-api-key")
OPENLINEAGE_API_KEY="${OPENLINEAGE_API_KEY:-$DD_API_KEY}"
export DD_API_KEY OPENLINEAGE_API_KEY

if [ -n "${EXAMPLE_HOST}" ]; then
    export EXAMPLE_TARGETS="${EXAMPLE_TARGETS:-a,b}"
else
    export EXAMPLE_TARGETS="${EXAMPLE_TARGETS:-a}"
fi

export AIRFLOW__OPENLINEAGE__NAMESPACE=${AIRFLOW_ENV_NAME}
export OPENLINEAGE_CLIENT_LOGGING=DEBUG

export OPENLINEAGE_URL="${OPENLINEAGE_URL:-https://data-obs-intake.datad0g.com}"
export OPENLINEAGE_API_KEY="${OPENLINEAGE_API_KEY:-$DD_API_KEY}"
export SECOND_OPENLINEAGE_URL="${SECOND_OPENLINEAGE_URL:-https://data-obs-intake.datadoghq.com}"

export OPENLINEAGE__TRANSPORT__TYPE=composite
export OPENLINEAGE__TRANSPORT__CONTINUE_ON_FAILURE=true
export OPENLINEAGE__TRANSPORT__TRANSPORTS__CONSOLE__TYPE=console

export OPENLINEAGE__TRANSPORT__TRANSPORTS__STAGING__TYPE=http
export OPENLINEAGE__TRANSPORT__TRANSPORTS__STAGING__URL="${OPENLINEAGE_URL}"
export OPENLINEAGE__TRANSPORT__TRANSPORTS__STAGING__AUTH__TYPE=api_key
export OPENLINEAGE__TRANSPORT__TRANSPORTS__STAGING__AUTH__API_KEY="${OPENLINEAGE_API_KEY}"

export OPENLINEAGE__TRANSPORT__TRANSPORTS__SECOND__TYPE=http
export OPENLINEAGE__TRANSPORT__TRANSPORTS__SECOND__URL="${SECOND_OPENLINEAGE_URL}"
export OPENLINEAGE__TRANSPORT__TRANSPORTS__SECOND__AUTH__TYPE=api_key
export OPENLINEAGE__TRANSPORT__TRANSPORTS__SECOND__AUTH__API_KEY="${SECOND_DD_API_KEY}"

python - <<'PY'
print("OPENLINEAGE_URL=https://ignored.invalid")
PY

unset PIP_CONSTRAINT || true
python -m pip install apache-airflow-providers-openlineage==2.14.0 apache-airflow-providers-common-sql==1.32.0 --no-deps || true
