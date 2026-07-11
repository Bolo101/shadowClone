"""
clone.py – Cœur du clonage : pilotage du sous-processus `dd`.

Le clonage bit-à-bit est délégué à `dd`, plus robuste et plus rapide qu'une
boucle read()/write() en Python pur (conv=noerror,sync permet de sauter les
secteurs défectueux du disque source sans interrompre tout le clonage).
`status=progress` fait écrire à dd, sur stderr, une ligne d'avancement
régulière que l'on parse pour calculer pourcentage / vitesse / ETA.
"""
from __future__ import annotations

import re
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from utils import get_disk_size, unmount_all_partitions

# Ligne typique produite par dd avec status=progress, ex:
# "123456789 bytes (123 MB, 118 MiB) copied, 4 s, 30.9 MB/s"
_DD_PROGRESS_RE = re.compile(r"^(\d+)\s+bytes")


class CloneError(Exception):
    """Erreur bloquante survenue pendant le clonage."""


class SizeMismatchError(CloneError):
    """Le disque de destination est plus petit que le disque source."""


@dataclass
class CloneProgress:
    copied_bytes: int
    total_bytes: int
    percent: float
    speed_mb_s: float
    eta_seconds: float
    elapsed_seconds: float


class CloneJob:
    """
    Représente une opération de clonage en cours, avec possibilité
    d'annulation depuis un autre thread (ex : bouton "Annuler" du GUI).
    """

    def __init__(self) -> None:
        self._cancel_event = threading.Event()
        self._process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()

    def cancel(self) -> None:
        self._cancel_event.set()
        with self._lock:
            if self._process and self._process.poll() is None:
                self._process.terminate()

    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def run(
        self,
        source_dev: str,
        dest_dev: str,
        block_size: str = "4M",
        progress_callback: Optional[Callable[[CloneProgress], None]] = None,
        log_func: Optional[Callable[[str], None]] = None,
    ) -> None:
        """
        Effectue le clonage bit-à-bit de source_dev vers dest_dev.
        `source_dev`/`dest_dev` sont des noms courts ("sda") ou des chemins
        complets ("/dev/sda") — les deux formats sont acceptés.

        Lève CloneError (ou SizeMismatchError) en cas de problème.
        """
        source_name = source_dev.split("/")[-1]
        dest_name = dest_dev.split("/")[-1]
        source_path = f"/dev/{source_name}"
        dest_path = f"/dev/{dest_name}"

        def log(msg: str) -> None:
            if log_func:
                log_func(msg)

        log(f"Vérification des tailles ({source_path} -> {dest_path})...")
        size_src = get_disk_size(source_name)
        size_dst = get_disk_size(dest_name)

        if size_src <= 0:
            raise CloneError(f"Impossible de lire la taille du disque source {source_path}.")
        if size_dst <= 0:
            raise CloneError(f"Impossible de lire la taille du disque destination {dest_path}.")
        if size_dst < size_src:
            raise SizeMismatchError(
                f"Le disque de destination ({dest_path}, {size_dst} o) est plus "
                f"petit que le disque source ({source_path}, {size_src} o)."
            )

        log("Démontage des partitions montées...")
        unmount_all_partitions(source_name, log_func=log)
        unmount_all_partitions(dest_name, log_func=log)

        log(f"Démarrage du clonage : {source_path} -> {dest_path} ({size_src} octets, bloc {block_size})")

        cmd = [
            "dd",
            f"if={source_path}",
            f"of={dest_path}",
            f"bs={block_size}",
            "conv=noerror,sync",
            "status=progress",
        ]

        with self._lock:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        process = self._process
        start_time = time.time()
        last_copied = 0

        # dd écrit ses lignes de progression avec un retour chariot '\r' et
        # non un saut de ligne : il faut donc lire caractère par caractère
        # (ou par petits blocs) pour ne pas rester bloqué en attendant '\n'.
        buffer = ""
        assert process.stderr is not None
        while True:
            if self.is_cancelled():
                process.terminate()
                log("Clonage annulé par l'utilisateur.")
                raise CloneError("Clonage annulé par l'utilisateur.")

            chunk = process.stderr.read(256)
            if not chunk:
                if process.poll() is not None:
                    break
                continue

            buffer += chunk
            *complete, buffer = re.split(r"[\r\n]", buffer)
            for line in complete:
                line = line.strip()
                if not line:
                    continue
                m = _DD_PROGRESS_RE.match(line)
                if not m:
                    # Ligne finale récapitulative de dd, utile pour le log
                    if "copied" in line:
                        log(f"dd: {line}")
                    continue

                copied = int(m.group(1))
                last_copied = copied
                elapsed = max(time.time() - start_time, 0.001)
                percent = min(100.0, (copied / size_src) * 100)
                speed_mb_s = (copied / (1024 * 1024)) / elapsed
                remaining_bytes = max(size_src - copied, 0)
                eta = (remaining_bytes / (1024 * 1024)) / speed_mb_s if speed_mb_s > 0 else 0.0

                if progress_callback:
                    progress_callback(CloneProgress(
                        copied_bytes=copied,
                        total_bytes=size_src,
                        percent=percent,
                        speed_mb_s=speed_mb_s,
                        eta_seconds=eta,
                        elapsed_seconds=elapsed,
                    ))

        return_code = process.wait()
        with self._lock:
            self._process = None

        if self.is_cancelled():
            raise CloneError("Clonage annulé par l'utilisateur.")

        if return_code != 0:
            raise CloneError(f"dd a échoué avec le code de retour {return_code}.")

        # Rapport final à 100 % même si la dernière ligne de dd n'était pas
        # tombée pile sur un multiple lisible juste avant.
        if progress_callback:
            elapsed = max(time.time() - start_time, 0.001)
            progress_callback(CloneProgress(
                copied_bytes=size_src,
                total_bytes=size_src,
                percent=100.0,
                speed_mb_s=(size_src / (1024 * 1024)) / elapsed,
                eta_seconds=0.0,
                elapsed_seconds=elapsed,
            ))

        log("Synchronisation finale des données sur le disque (sync)...")
        subprocess.run(["sync"], check=False)
        log("Clonage terminé avec succès.")


def verify_clone(
    source_dev: str,
    dest_dev: str,
    progress_callback: Optional[Callable[[CloneProgress], None]] = None,
    log_func: Optional[Callable[[str], None]] = None,
    cancel_job: Optional[CloneJob] = None,
) -> bool:
    """
    Vérifie l'identité bit-à-bit des deux disques sur la taille du disque
    source (comparaison brute via `cmp`). Retourne True si identiques.

    Optionnel : appelé après CloneJob.run() si l'utilisateur a activé la
    vérification post-clonage dans les paramètres.
    """
    source_name = source_dev.split("/")[-1]
    dest_name = dest_dev.split("/")[-1]
    source_path = f"/dev/{source_name}"
    dest_path = f"/dev/{dest_name}"

    def log(msg: str) -> None:
        if log_func:
            log_func(msg)

    size_src = get_disk_size(source_name)
    if size_src <= 0:
        raise CloneError(f"Impossible de lire la taille du disque source {source_path}.")

    log("Vérification post-clonage en cours (comparaison bit-à-bit)...")
    process = subprocess.Popen(
        ["cmp", "-s", source_path, dest_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    start = time.time()
    while process.poll() is None:
        if cancel_job and cancel_job.is_cancelled():
            process.terminate()
            raise CloneError("Vérification annulée par l'utilisateur.")
        elapsed = time.time() - start
        if progress_callback:
            # cmp ne donne pas d'avancement fin ; on communique juste que la
            # vérification est en cours (le GUI peut afficher un indicateur
            # indéterminé pendant cette phase).
            progress_callback(CloneProgress(
                copied_bytes=0, total_bytes=size_src, percent=-1.0,
                speed_mb_s=0.0, eta_seconds=0.0, elapsed_seconds=elapsed,
            ))
        time.sleep(0.5)

    identical = process.returncode == 0
    if identical:
        log("Vérification réussie : les disques sont identiques.")
    else:
        log("ÉCHEC de la vérification : les disques diffèrent.")
    return identical