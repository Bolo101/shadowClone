"""
port_detector.py – Assistant de détection de port physique.

Principe : pour affecter un port physique du hub USB comme "source" ou
"destination", on demande à l'utilisateur de débrancher puis de rebrancher
un disque quelconque sur ce port. On compare l'ensemble des périphériques
USB visibles avant/après pour repérer le nouveau venu, puis on lit sa
propriété udev ID_PATH : cette valeur identifie le port physique et reste
stable quel que soit le disque qui y sera branché par la suite.
"""
from __future__ import annotations

import time
from typing import Callable, Optional

from utils import DiskInfo, list_block_devices, snapshot_usb_devnames


class DetectionTimeout(Exception):
    """Levée quand aucun nouveau disque n'a été détecté dans le délai imparti."""


class DetectionCancelled(Exception):
    """Levée quand l'utilisateur annule la détection en cours."""


def wait_for_unplugged(
    timeout: int = 60,
    poll_interval: float = 1.0,
    cancel_check: Optional[Callable[[], bool]] = None,
    status_cb: Optional[Callable[[str], None]] = None,
) -> set:
    """
    Attend que plus aucun disque USB ne soit branché (état de repos), afin
    d'obtenir une base propre avant de demander à l'utilisateur de brancher
    le disque de test. Retourne l'ensemble (vide, idéalement) des devnames
    USB restants au bout du délai — utilisé tel quel comme référence.
    """
    deadline = time.time() + timeout
    baseline = snapshot_usb_devnames()
    while baseline and time.time() < deadline:
        if cancel_check and cancel_check():
            raise DetectionCancelled()
        if status_cb:
            status_cb(f"En attente du débranchement ({len(baseline)} disque(s) encore présent(s))...")
        time.sleep(poll_interval)
        baseline = snapshot_usb_devnames()
    return baseline


def wait_for_new_disk(
    baseline: set,
    timeout: int = 60,
    poll_interval: float = 1.0,
    settle_delay: float = 2.0,
    cancel_check: Optional[Callable[[], bool]] = None,
    status_cb: Optional[Callable[[str], None]] = None,
) -> DiskInfo:
    """
    Attend l'apparition d'un nouveau disque USB par rapport à `baseline`.
    Retourne le DiskInfo correspondant une fois détecté (après un court
    délai de stabilisation pour laisser udev renseigner ID_PATH/modèle/série).

    Lève DetectionTimeout si rien n'apparaît dans le délai imparti, ou
    DetectionCancelled si cancel_check() retourne True entre-temps.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cancel_check and cancel_check():
            raise DetectionCancelled()

        current = snapshot_usb_devnames()
        new_names = current - baseline
        if new_names:
            # Laisse le temps au noyau/udev de finir d'énumérer le périphérique
            time.sleep(settle_delay)
            disks = list_block_devices(usb_only=True)
            for disk in disks:
                if disk.devname in new_names and disk.id_path:
                    return disk
            # ID_PATH pas encore prêt : on retente au prochain tour
        if status_cb:
            status_cb("En attente du branchement du disque de test...")
        time.sleep(poll_interval)

    raise DetectionTimeout(
        "Aucun nouveau disque USB détecté dans le délai imparti."
    )


def run_detection_wizard(
    timeout: int = 60,
    cancel_check: Optional[Callable[[], bool]] = None,
    status_cb: Optional[Callable[[str], None]] = None,
) -> DiskInfo:
    """
    Séquence complète de détection d'un port :
      1. attend que le port soit libre (aucun disque test déjà branché dessus)
      2. attend le branchement d'un nouveau disque
      3. retourne ses informations, dont le id_path à enregistrer

    Cette fonction est bloquante : à appeler depuis un thread d'arrière-plan,
    jamais depuis le thread GUI principal.
    """
    baseline = wait_for_unplugged(
        timeout=timeout, cancel_check=cancel_check, status_cb=status_cb
    )
    return wait_for_new_disk(
        baseline, timeout=timeout, cancel_check=cancel_check, status_cb=status_cb
    )