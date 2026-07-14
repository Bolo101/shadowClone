"""
config_manager.py – Configuration persistante du cloneur de disque.

Stocke notamment :
* le port physique (identifiant udev ID_PATH) affecté à la source
* le port physique affecté à la destination
* des paramètres de clonage (taille de bloc, vérification post-clonage)

Le mot de passe administrateur est stocké séparément dans
/etc/disk_cloner/admin.cred via SecureCredentialStore.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional, Tuple

from secure_credentials import SecureCredentialStore

CONFIG_DIR = "/etc/disk_cloner"
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
ADMIN_CRED_FILE = os.path.join(CONFIG_DIR, "admin.cred")

DEFAULT_ADMIN_PASSWORD = "0000"
MIN_ADMIN_PASSWORD_LENGTH = 4

_DEFAULT_CONFIG: Dict[str, Any] = {
    "source_id_path": None,
    "source_label": None,
    "dest_id_path": None,
    "dest_label": None,
    "block_size": "4M",
    "verify_after_clone": False,
}

_store = SecureCredentialStore(
    path=ADMIN_CRED_FILE,
    default_password=DEFAULT_ADMIN_PASSWORD,
)


def _ensure_config_dir() -> None:
    os.makedirs(CONFIG_DIR, mode=0o750, exist_ok=True)


def load_config() -> Dict[str, Any]:
    _ensure_config_dir()
    if not os.path.isfile(CONFIG_FILE):
        save_config(_DEFAULT_CONFIG.copy())
        return _DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        data = {}

    merged = _DEFAULT_CONFIG.copy()
    merged.update(data)

    # Nettoyage silencieux d'anciens champs de mot de passe si présents
    merged.pop("admin_password_hash", None)
    merged.pop("admin_password_salt", None)
    return merged


def save_config(config: Dict[str, Any]) -> None:
    _ensure_config_dir()

    clean_config = dict(config)
    clean_config.pop("admin_password_hash", None)
    clean_config.pop("admin_password_salt", None)

    tmp_path = CONFIG_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(clean_config, f, indent=2, ensure_ascii=False)

    os.replace(tmp_path, CONFIG_FILE)

    try:
        os.chmod(CONFIG_FILE, 0o640)
    except OSError:
        pass


def _update(**kwargs) -> None:
    cfg = load_config()
    cfg.update(kwargs)
    save_config(cfg)


# -- Ports source / destination ---------------------------------------------

def get_source_id_path() -> Optional[str]:
    return load_config().get("source_id_path")


def set_source_id_path(id_path: str, label: str = "") -> None:
    _update(source_id_path=id_path, source_label=label)


def get_dest_id_path() -> Optional[str]:
    return load_config().get("dest_id_path")


def set_dest_id_path(id_path: str, label: str = "") -> None:
    _update(dest_id_path=id_path, dest_label=label)


def ports_configured() -> bool:
    cfg = load_config()
    return bool(cfg.get("source_id_path")) and bool(cfg.get("dest_id_path"))


# -- Paramètres de clonage --------------------------------------------------

def get_block_size() -> str:
    return load_config().get("block_size", "4M")


def set_block_size(value: str) -> None:
    _update(block_size=value)


def get_verify_after_clone() -> bool:
    return bool(load_config().get("verify_after_clone", False))


def set_verify_after_clone(value: bool) -> None:
    _update(verify_after_clone=bool(value))


# -- Mot de passe administrateur -------------------------------------------

def is_password_set() -> bool:
    return os.path.isfile(ADMIN_CRED_FILE)


def is_default_password() -> bool:
    return _store.is_default_password(DEFAULT_ADMIN_PASSWORD)


def set_password(password: str) -> None:
    if len(password) < MIN_ADMIN_PASSWORD_LENGTH:
        raise ValueError(
            f"Le mot de passe doit comporter au moins {MIN_ADMIN_PASSWORD_LENGTH} caractères."
        )

    ok, message = _store.force_set_password(password)
    if not ok:
        raise ValueError(message)


def verify_password(password: str) -> bool:
    ok, _wait = _store.verify(password)
    return ok


def verify_password_with_wait(password: str) -> Tuple[bool, int]:
    return _store.verify(password)


def change_password(old_password: str, new_password: str) -> bool:
    ok, _message = _store.change_password(old_password, new_password)
    return ok


def change_password_with_message(old_password: str, new_password: str) -> Tuple[bool, str]:
    return _store.change_password(old_password, new_password)