import sys
from pathlib import Path

# Add the parent directory (logging_install) to Python path
# This will be executed automatically for all tests in this directory
sys.path.insert(0, str(Path(__file__).parent.parent))
