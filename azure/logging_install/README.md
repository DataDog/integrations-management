# Overview
This project installs the Azure cloud infrastructure for Datadog's Automated Azure Log Forwarding product. 

For end users, the produced executable will run in an [Azure Cloud Shell](https://learn.microsoft.com/en-us/azure/cloud-shell/get-started/classic?tabs=azurecli) in bash mode. 

For development, you can run the script locally (assuming you have Azure CLI setup). 

During final testing, you should upload the executable into Azure Cloud Shell and run it there. 

# Dev Setup
### Azure CLI setup
```bash
brew install azure-cli
az login
```

### Dev Env Setup 
Run from the `logging_install` folder:
```bash
pyenv install 3.5.10
brew install pyenv-virtualenv
pyenv virtualenv 3.5.10 azlogginginstall
pyenv local azlogginginstall; pyenv shell azlogginginstall
pip install --upgrade pip==20.3.4
pip install -e '.[dev]'
```

### Testing
Run all tests
```bash
python -m pytest tests/ -v
```

### Build/Ship
Run from the `logging_install` folder:
Zip app into a single executable file `dist/azure_logging_install.pyz`

```bash
python -m zipapp src \
  -o dist/azure_logging_install.pyz \
  -p "/usr/bin/env python3" \
  -m "azure_logging_install.main:main"
chmod +x dist/azure_logging_install.pyz
```

### Execution
Usage
```bash
usage: azure_logging_install.pyz [-h]
  --management-group MANAGEMENT_GROUP \
  --control-plane-region CONTROL_PLANE_REGION \
  --control-plane-subscription CONTROL_PLANE_SUBSCRIPTION \
  --control-plane-resource-group CONTROL_PLANE_RESOURCE_GROUP \
  --monitored-subscriptions MONITORED_SUBSCRIPTIONS \
  --datadog-api-key DATADOG_API_KEY \
  [--datadog-site {datadoghq.com,datadoghq.eu,ap1.datadoghq.com,ap2.datadoghq.com,us3.datadoghq.com,us5.datadoghq.com,ddog-gov.com}] \
  [--resource-tag-filters RESOURCE_TAG_FILTERS] \
  [--pii-scrubber-rules PII_SCRUBBER_RULES] \
  [--datadog-telemetry] \
  [--log-level {DEBUG,INFO,WARNING,ERROR}]

Azure Log Forwarding Orchestration Installation Script

options:
  -h, --help            show this help message and exit
  -mg MANAGEMENT_GROUP, --management-group MANAGEMENT_GROUP
                        Management group ID to deploy under (required)
  --control-plane-region CONTROL_PLANE_REGION
                        Azure region for the control plane (e.g., eastus, westus2) (required)
  --control-plane-subscription CONTROL_PLANE_SUBSCRIPTION
                        Subscription ID where the control plane will be deployed (required)
  --control-plane-resource-group CONTROL_PLANE_RESOURCE_GROUP
                        Resource group name for the control plane (required)
  --monitored-subscriptions MONITORED_SUBSCRIPTIONS
                        Comma-separated list of subscription IDs to monitor for log forwarding (required)
  --datadog-api-key DATADOG_API_KEY
                        Datadog API key (required)
  --datadog-site {datadoghq.com,datadoghq.eu,ap1.datadoghq.com,ap2.datadoghq.com,us3.datadoghq.com,us5.datadoghq.com,ddog-gov.com}
                        Datadog site (default: datadoghq.com)
  --resource-tag-filters RESOURCE_TAG_FILTERS
                        Comma separated list of tags to filter resources by
  --pii-scrubber-rules PII_SCRUBBER_RULES
                        YAML formatted list of PII Scrubber Rules
  --datadog-telemetry   Enable Datadog telemetry
  --log-level {DEBUG,INFO,WARNING,ERROR}
                        Set the log level (default: INFO)
```

Sample
```bash
./azure_logging_install.pyz \
  -mg "/providers/Microsoft.Management/managementGroups/Azure-Integrations-Mg" \
  --control-plane-region eastus \
  --control-plane-subscription 0b62a232-b8db-4380-9da6-640f7272ed6d \
  --control-plane-resource-group datadog_control_plane \
  --monitored-subscriptions "0b62a232-b8db-4380-9da6-640f7272ed6d,34464906-34fe-401e-a420-79bd0ce2a1da" \
  --datadog-api-key <DD_API_KEY> \
  --datadog-site datadoghq.com \
  --resource-tag-filters "datadog:true" \
  --log-level DEBUG
```


Execute the script during dev/test
```bash
python -m azure_logging_install [args] 
```