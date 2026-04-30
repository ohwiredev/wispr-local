import sys
import os
from pathlib import Path

def get_app_root() -> Path:
    """Returns the root directory for application data (models, config).
    In development, it's the project root.
    In production (frozen), it's in the user's Local AppData to ensure write permissions.
    """
    if getattr(sys, 'frozen', False):
        # Use Local AppData for persistent files (models, config)
        app_data = os.environ.get("LOCALAPPDATA")
        if app_data:
            path = Path(app_data) / "WisprLocal"
        else:
            path = Path.home() / ".wispr_local"
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    # Assuming this file is in wispr_local/paths.py
    return Path(__file__).parent.parent.absolute()

def get_models_path() -> Path:
    return get_app_root() / "models"

def get_settings_path() -> Path:
    return get_app_root() / "config" / "settings.json"
