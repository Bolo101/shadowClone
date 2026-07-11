"""
utils.py – Fonctions bas niveau de détection et d'inspection des disques.

Toute la logique de correspondance "port physique -> /dev/sdX" repose sur
la propriété udev ID_PATH, qui identifie la topologie physique du port USB
(hub, numéro de port) et NE CHANGE PAS lorsque l'on débranche/rebranche un
disque différent sur le même port. C'est ce qui permet de configurer une
bonne fois pour toutes "le port de gauche = source" et "le port de droite
= destination" depuis l'interface d'administration.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional


# ── Modèle de données ──────────────────────────────────────────────────────
@dataclass
class DiskInfo:
    devname: str          # ex: "sda"
    path: str              # ex: "/dev/sda"
    size_bytes: int
    model: str
    serial: str
    tran: str               # "usb", "sata", ...
    id_path: str            # identifiant udev stable du port physique

    @property
    def size_human(self) -> str:
        return human_size(self.size_bytes)


# ── Helpers généraux ────────────────────────────────────────────────────────
def human_size(num_bytes: int) -> str:
    """Convertit un nombre d'octets en chaîne lisible (Go/To)."""
    try:
        num_bytes = float(num_bytes)
    except (TypeError, ValueError):
        return "?"
    for unit in ("o", "Ko", "Mo", "Go", "To", "Po"):
        if num_bytes < 1024.0:
            return f"{num_bytes:.1f} {unit}" if unit != "o" else f"{int(num_bytes)} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} Eo"


def _run(cmd: List[str], timeout: int = 10) -> str:
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, check=False
    )
    return result.stdout


# ── Listing des disques ─────────────────────────────────────────────────────
def list_block_devices(usb_only: bool = True) -> List[DiskInfo]:
    """
    Retourne la liste des disques (type=disk) actuellement visibles par le
    noyau, avec leurs métadonnées. Si usb_only=True (par défaut), ne renvoie
    que les disques connectés en USB — c'est le cas d'usage de la borne :
    on ne veut jamais proposer accidentellement le disque système interne.
    """
    out = _run([
        "lsblk", "-J", "-b", "-o",
        "NAME,PATH,SIZE,MODEL,SERIAL,TRAN,TYPE,RM",
    ])
    try:
        data = json.loads(out or "{}")
    except json.JSONDecodeError:
        return []

    disks: List[DiskInfo] = []
    for dev in data.get("blockdevices", []):
        if dev.get("type") != "disk":
            continue
        tran = (dev.get("tran") or "").lower()
        if usb_only and tran != "usb":
            continue

        devname = dev.get("name") or ""
        path = dev.get("path") or f"/dev/{devname}"
        size_bytes = int(dev.get("size") or 0)
        model = (dev.get("model") or "Inconnu").strip()
        serial = (dev.get("serial") or "").strip()

        id_path = get_id_path(devname) or ""

        disks.append(DiskInfo(
            devname=devname,
            path=path,
            size_bytes=size_bytes,
            model=model or "Inconnu",
            serial=serial or "N/A",
            tran=tran,
            id_path=id_path,
        ))
    return disks


def get_id_path(devname: str) -> Optional[str]:
    """
    Retourne la propriété udev ID_PATH du périphérique (identifiant stable
    du port physique), ou None si indisponible.
    """
    devname = devname.lstrip("/").removeprefix("dev/")
    out = _run(["udevadm", "info", "--query=property", f"--name=/dev/{devname}"])
    for line in out.splitlines():
        if line.startswith("ID_PATH="):
            return line.split("=", 1)[1].strip()
    return None


def find_disk_by_id_path(id_path: str, usb_only: bool = True) -> Optional[DiskInfo]:
    """Retourne le DiskInfo actuellement branché sur le port identifié par id_path."""
    if not id_path:
        return None
    for disk in list_block_devices(usb_only=usb_only):
        if disk.id_path == id_path:
            return disk
    return None


def get_base_disk(devpath: str) -> str:
    """
    Retourne le disque de base (ex: /dev/sda) à partir d'un chemin de
    partition (ex: /dev/sda1). Sans effet si devpath est déjà un disque.
    """
    m = re.match(r"^(/dev/[a-zA-Z]+)\d*$", devpath)
    return m.group(1) if m else devpath


def list_partitions(devname: str) -> List[str]:
    """Retourne les chemins /dev/... de toutes les partitions d'un disque."""
    devname = devname.lstrip("/").removeprefix("dev/")
    out = _run(["lsblk", "-ln", "-o", "NAME", f"/dev/{devname}"])
    names = [n for n in out.splitlines() if n.strip()]
    return [f"/dev/{n}" for n in names if n != devname]


def unmount_all_partitions(devname: str, log_func=None) -> None:
    """Démonte toutes les partitions montées d'un disque avant clonage."""
    for part in list_partitions(devname):
        try:
            res = subprocess.run(
                ["umount", part], capture_output=True, text=True, check=False
            )
            if log_func and res.returncode == 0:
                log_func(f"Partition démontée : {part}")
        except (subprocess.SubprocessError, OSError) as e:
            if log_func:
                log_func(f"Impossible de démonter {part} : {e}")


def get_disk_size(devname: str) -> int:
    """Taille en octets d'un disque via blockdev --getsize64."""
    devname = devname.lstrip("/").removeprefix("dev/")
    out = _run(["blockdev", "--getsize64", f"/dev/{devname}"])
    try:
        return int(out.strip())
    except ValueError:
        return 0


def snapshot_usb_devnames() -> set:
    """Ensemble des noms de périphériques (sda, sdb, ...) USB actuellement branchés."""
    return {d.devname for d in list_block_devices(usb_only=True)}