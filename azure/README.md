# Dev Setup
The various Azure integration management tools share a development environment.

### Azure CLI setup
```bash
brew update
brew install azure-cli
az login
```

### Dev Setup

#### Environment
Run from the `azure` folder:
```bash
brew update
brew upgrade pyenv || brew install pyenv
pyenv install 3.9.22
brew install pyenv-virtualenv
pyenv virtualenv 3.9.22 azintegrationmanagement
pyenv local azintegrationmanagement
pyenv shell azintegrationmanagement
pip install -r 'dev_requirements.txt'
```


#### IDE (Recommended)
- Install VS Code.
- Within VS Code, install the following extensions:
  - Python
  - Ruff
- VS Code `settings.json` file already exists within this directory.
