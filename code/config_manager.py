"""
config_manager.py – Configuration persistante du cloneur de disque.

Stocke notamment :
  * le port physique (identifiant udev ID_PATH) affecté a la source
  * le port physique affecte a la destination
  * le hash du mot de passe administrateur
  * des parametres de clonage (taille de bloc, verification post-clonage...)

Fichier de configuration : /etc/disk_cloner/config.json
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
from typing import Any, Dict, Optional

CONFIG_DIR = "/etc/disk_cloner"
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

_DEFAULT_CONFIG: Dict[str, Any] = {
    "source_id_path": None,
    "source_label": None,       # dernier modele/serie vus sur ce port (informatif)
    "dest_id_path": None,
    "dest_label": None,
    "admin_password_hash": None,
    "admin_password_salt": None,
    "block_size": "4M",
    "verify_after_clone": False,
}


def _ensure_config_dir() -> None:
    os.makedirs(CONFIG_DIR, mode=0o750, exist_ok=True)


def load_config() -> Dict[str, Any]:
    _ensure_config_dir()
    if not os.path.isfile(CONFIG_FILE):
        save_config(_DEFAULT_CONFIG.copy())
        return _DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        data = {}
    merged = _DEFAULT_CONFIG.copy()
    merged.update(data)
    return merged


def save_config(config: Dict[str, Any]) -> None:
    _ensure_config_dir()
    tmp_path = CONFIG_FILE + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
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


# -- Parametres de clonage ----------------------------------------------------
def get_block_size() -> str:
    return load_config().get("block_size", "4M")


def set_block_size(value: str) -> None:
    _update(block_size=value)


def get_verify_after_clone() -> bool:
    return bool(load_config().get("verify_after_clone", False))


def set_verify_after_clone(value: bool) -> None:
    _update(verify_after_clone=bool(value))


# -- Mot de passe administrateur --------------------------------------------
def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def is_password_set() -> bool:
    cfg = load_config()
    return bool(cfg.get("admin_password_hash"))


def set_password(password: str) -> None:
    salt = secrets.token_hex(16)
    _update(admin_password_salt=salt, admin_password_hash=_hash_password(password, salt))


def verify_password(password: str) -> bool:
    cfg = load_config()
    salt = cfg.get("admin_password_salt")
    stored_hash = cfg.get("admin_password_hash")
    if not salt or not stored_hash:
        return False
    return secrets.compare_digest(_hash_password(password, salt), stored_hash)


def change_password(old_password: str, new_password: str) -> bool:
    if not verify_password(old_password):
        return False
    set_password(new_password)
    return True