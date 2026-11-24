import os
import sys
from pathlib import Path

project = Path.home() / "tracker_"
sys.path.insert(0, str(project))
os.environ["DJANGO_DEBUG"] = "0"

from currencytracker.wsgi import application
