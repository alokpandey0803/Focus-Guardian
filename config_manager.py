"""
Configuration manager — saves and loads blocked sites, apps, and settings to/from JSON.
"""
import json
import os

import app_paths

app_paths.migrate_legacy_file("config.json", os.path.dirname(__file__))
CONFIG_FILE = os.path.join(app_paths.data_dir(), "config.json")

DEFAULT_CONFIG = {
    "blocked_websites": [],
    "blocked_apps": [],
    "timer_minutes": 25,
    "lock_in_active": False,
    "lock_in_password": "",
    "notifications_enabled": True,
    "block_adult_content": False,  # opt-in — off until the user ticks it
}


def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
            # Fill in any missing keys from defaults
            for key, val in DEFAULT_CONFIG.items():
                data.setdefault(key, val)
            return data
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULT_CONFIG)


def save_config(config: dict) -> None:
    app_paths.atomic_write_json(CONFIG_FILE, config)
