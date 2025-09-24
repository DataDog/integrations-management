# Dev Setup
The various azure integration management projects share a development environment

### Azure CLI setup
```bash
brew install azure-cli
az login
```

### Dev Env Setup 
Run from the `azure` folder:
```bash
pyenv install 3.9.22
brew install pyenv-virtualenv
pyenv virtualenv 3.9.22 azintegrationmanagement
pyenv local azintegrationmanagement; pyenv shell azintegrationmanagement
pip install -r 'dev_requirements.txt'
```
