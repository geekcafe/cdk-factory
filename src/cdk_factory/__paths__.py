import os
import sys
from pathlib import Path

project_root = Path(__file__).parents[2].absolute()
print(f"project root: {project_root}")
## needed for discovery based top level execution
sys.path.insert(0, os.path.join(project_root, "src"))
sys.path.insert(0, os.path.join(project_root, "src", "cdk_factory"))
