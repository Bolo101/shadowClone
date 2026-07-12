"""
log_handler.py - Journalisation avec rotation par volumetrie (cloneur de disque).

Rotation : des que disk_clone.log depasse MAX_LOG_SIZE, il est renomme
           disk_clone.log.YYYYMMDD_HHMMSS et un nouveau fichier demarre.
           Les MAX_ROTATED_FILES plus anciens rotated sont supprimes.

Structure :
  /var/log/disk_cloner/disk_clone.log          <- journal courant
  /var/log/disk_cloner/disk_clone.log.*        <- journaux tournes
  /var/log/disk_cloner/pdf/                    <- rapports PDF
"""
import glob
import logging
import os
import sys
import textwrap
from datetime import datetime
from typing import List

# -- Constantes ---------------------------------------------------------------
LOG_DIR          = "/var/log/disk_cloner"
LOG_FILE         = os.path.join(LOG_DIR, "disk_clone.log")
PDF_DIR          = os.path.join(LOG_DIR, "pdf")
MAX_LOG_SIZE     = 10 * 1024 * 1024   # 10 Mo
MAX_ROTATED_FILES = 10

# -- Etat de session ------------------------------------------------------------
_session_logs: List[str] = []
_session_active: bool    = False


# -- Handler de capture de session ---------------------------------------------
class SessionCapturingHandler(logging.Handler):
    """Capture tous les messages de log pendant la session courante."""
    def emit(self, record: logging.LogRecord) -> None:
        global _session_logs, _session_active
        if _session_active:
            ts  = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
            msg = f"[{ts}] {record.levelname}: {record.getMessage()}"
            _session_logs.append(msg)


# -- Rotation des logs ----------------------------------------------------------
def _rotate_if_needed() -> None:
    """Rotate le fichier de log courant si sa taille depasse MAX_LOG_SIZE."""
    if not os.path.isfile(LOG_FILE):
        return
    if os.path.getsize(LOG_FILE) < MAX_LOG_SIZE:
        return

    ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
    rotated = f"{LOG_FILE}.{ts}"
    try:
        os.rename(LOG_FILE, rotated)
    except OSError as e:
        print(f"[log_handler] Impossible de pivoter le log : {e}", file=sys.stderr)
        return

    pattern  = f"{LOG_FILE}.*"
    existing = sorted(glob.glob(pattern))
    while len(existing) > MAX_ROTATED_FILES:
        oldest = existing.pop(0)
        try:
            os.remove(oldest)
        except OSError:
            pass


def _setup_file_handler() -> None:
    """(Re)cree le FileHandler apres rotation ou au demarrage."""
    global _file_handler

    try:
        if _file_handler:
            _logger.removeHandler(_file_handler)
            _file_handler.close()
    except NameError:
        pass

    try:
        handler = logging.FileHandler(LOG_FILE)
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        _logger.addHandler(handler)
        _file_handler = handler
    except (PermissionError, OSError) as e:
        print(f"[log_handler] Impossible d'ouvrir le fichier de log : {e}", file=sys.stderr)


# -- Initialisation du logger ---------------------------------------------------
os.makedirs(LOG_DIR, mode=0o750, exist_ok=True)
os.makedirs(PDF_DIR, mode=0o750, exist_ok=True)

_logger = logging.getLogger("disk_cloner")
_logger.setLevel(logging.INFO)
_logger.propagate = False

_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
_logger.addHandler(_console_handler)

_session_handler = SessionCapturingHandler()
_logger.addHandler(_session_handler)

_file_handler = None
_rotate_if_needed()
_setup_file_handler()


# -- API de journalisation -------------------------------------------------------
def log_info(message: str) -> None:
    _logger.info(message)


def log_error(message: str) -> None:
    _logger.error(message)


def log_warning(message: str) -> None:
    _logger.warning(message)


def log_clone_operation(source_id: str, dest_id: str, size_bytes: int) -> None:
    from utils import human_size
    msg = (f"Clonage - source: {source_id} | destination: {dest_id} | "
           f"taille: {human_size(size_bytes)}")
    _logger.info(msg)


def log_clone_completed(source_id: str, dest_id: str, duration_s: float) -> None:
    _logger.info(
        f"Clonage termine : {source_id} -> {dest_id} en {int(duration_s)} s"
    )


def log_clone_failed(source_id: str, dest_id: str, reason: str) -> None:
    _logger.error(f"Clonage ECHOUE : {source_id} -> {dest_id} | raison : {reason}")


def log_verification_result(source_id: str, dest_id: str, success: bool) -> None:
    status = "REUSSIE" if success else "ECHEC"
    _logger.info(f"Verification post-clonage {status} : {source_id} -> {dest_id}")


def session_start() -> None:
    global _session_logs, _session_active
    _session_logs   = []
    _session_active = True

    _rotate_if_needed()
    _setup_file_handler()

    sep = "=" * 80
    ts  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"\n{sep}\nSESSION START: {ts}\n{sep}\n")
    except OSError as e:
        _logger.error(f"Impossible d'ecrire le debut de session : {e}")

    log_info(f"Nouvelle session demarree a {ts}")


def session_end() -> None:
    global _session_active
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_info(f"Session terminee a {ts}")
    _session_active = False

    sep = "=" * 80
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"\n{sep}\nSESSION END: {ts}\n{sep}\n\n")
    except OSError as e:
        _logger.error(f"Impossible d'ecrire la fin de session : {e}")


def log_application_exit(exit_method: str = "Bouton Quitter") -> None:
    log_info(f"Application fermee via : {exit_method}")
    session_end()


def log_clone_process_stopped() -> None:
    log_info("Processus de clonage arrete par l'utilisateur.")


def get_current_session_logs() -> List[str]:
    return _session_logs.copy()


def is_session_active() -> bool:
    return _session_active


def get_all_log_files() -> List[str]:
    """Retourne la liste de tous les fichiers de log (courant + tournes), tries du plus recent au plus ancien."""
    files = []
    if os.path.isfile(LOG_FILE):
        files.append(LOG_FILE)
    rotated = sorted(glob.glob(f"{LOG_FILE}.*"), reverse=True)
    files.extend(rotated)
    return files


def purge_logs() -> None:
    """Supprime tous les fichiers de log (courant + tournes). Reserve a l'admin."""
    for f in get_all_log_files():
        try:
            os.remove(f)
        except OSError as e:
            _logger.error(f"Impossible de supprimer {f} : {e}")
    _setup_file_handler()
    log_info("Logs purges par l'administrateur.")


# -- Generation PDF ---------------------------------------------------------------
def generate_session_pdf(output_path: str = None) -> str:
    """Genere un PDF du rapport de session courante. Retourne le chemin du PDF."""
    session_logs = get_current_session_logs()
    if not session_logs:
        raise ValueError("Aucun log de session disponible.")

    if output_path is None:
        ts           = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_filename = f"session_{ts}.pdf"
        output_path  = os.path.join(PDF_DIR, pdf_filename)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    _create_simple_pdf(
        output_path,
        "Rapport de session - Clonage de disques",
        session_logs,
        f"Genere le : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Entrees de log : {len(session_logs)}",
    )
    log_info(f"PDF de session genere : {output_path}")
    return output_path


def generate_log_file_pdf(output_path: str = None) -> str:
    """Genere un PDF consolide de tous les logs (courant + tournes). Retourne le chemin du PDF."""
    all_lines: List[str] = []
    for log_file in get_all_log_files():
        try:
            with open(log_file, "r", errors="replace") as f:
                all_lines.append(f"{'='*60}")
                all_lines.append(f"Fichier : {os.path.basename(log_file)}")
                all_lines.append(f"{'='*60}")
                all_lines.extend(f.read().splitlines())
        except OSError as e:
            all_lines.append(f"[Erreur lecture {log_file} : {e}]")

    if not all_lines:
        raise ValueError("Aucun log disponible.")

    if output_path is None:
        ts           = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_filename = f"logs_complets_{ts}.pdf"
        output_path  = os.path.join(PDF_DIR, pdf_filename)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    _create_simple_pdf(
        output_path,
        "Logs complets - Clonage de disques",
        all_lines,
        f"Genere le : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Fichiers sources : {len(get_all_log_files())}",
        f"Lignes totales : {len(all_lines)}",
    )
    log_info(f"PDF logs complets genere : {output_path}")
    return output_path


# -- Construction PDF bas niveau (stdlib uniquement) -----------------------------
def _escape_pdf_string(text: str) -> str:
    if text is None:
        return ""
    text = str(text)
    text = text.replace("\\", "\\\\")
    text = text.replace("(", "\\(")
    text = text.replace(")", "\\)")
    text = text.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    return "".join(c if 32 <= ord(c) <= 126 else " " for c in text)


def _create_simple_pdf(pdf_path: str, title: str, lines: List[str], *info_lines: str) -> None:
    LINES_PER_PAGE = 55
    wrapped: List[str] = []
    for i, line in enumerate(lines, 1):
        prefix = f"{i:4d}: "
        avail  = 90 - len(prefix)
        for j, part in enumerate(textwrap.wrap(line or " ", avail, break_long_words=True) or [" "]):
            wrapped.append(f"{prefix if j == 0 else '      '}{part}")

    pages = [wrapped[i: i + LINES_PER_PAGE] for i in range(0, max(1, len(wrapped)), LINES_PER_PAGE)]

    objects: List[str] = []

    def add(obj: str) -> int:
        objects.append(obj)
        return len(objects)

    catalog_id  = add("")
    pages_id    = add("")
    font_id     = add(
        "3 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>\nendobj"
    )

    page_ids: List[int] = []
    stream_ids: List[int] = []

    for p_idx, page_lines in enumerate(pages):
        is_first = (p_idx == 0)
        page_num = p_idx + 1

        content_lines: List[str] = ["BT", "/F1 8 Tf"]
        if is_first:
            content_lines += [
                "50 750 Td", "/F1 14 Tf",
                f"({_escape_pdf_string(title)}) Tj",
                "/F1 9 Tf",
            ]
            for il in info_lines:
                content_lines += ["0 -14 Td", f"({_escape_pdf_string(il)}) Tj"]
            content_lines += ["0 -18 Td", "/F1 8 Tf"]
        else:
            content_lines += [
                "50 750 Td", "/F1 11 Tf",
                f"({_escape_pdf_string(f'{title} - page {page_num}')}) Tj",
                "0 -20 Td", "/F1 8 Tf",
            ]

        for cl in page_lines:
            content_lines += ["0 -11 Td", f"({_escape_pdf_string(cl)}) Tj"]

        content_lines += ["50 25 Td", "/F1 7 Tf",
                          f"(Page {page_num}/{len(pages)}) Tj", "ET"]
        stream_body = "\n".join(content_lines)

        sid = add(
            f"{len(objects)+1} 0 obj\n<< /Length {len(stream_body)} >>\n"
            f"stream\n{stream_body}\nendstream\nendobj"
        )
        stream_ids.append(sid)

        pid = add(
            f"{len(objects)+1} 0 obj\n"
            f"<< /Type /Page /Parent {pages_id} 0 R "
            f"/MediaBox [0 0 612 792] "
            f"/Contents {sid} 0 R "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>\n"
            f"endobj"
        )
        page_ids.append(pid)

    objects[catalog_id - 1] = (
        f"1 0 obj\n<< /Type /Catalog /Pages {pages_id} 0 R >>\nendobj"
    )
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects[pages_id - 1] = (
        f"2 0 obj\n<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>\nendobj"
    )

    numbered: List[str] = []
    for i, obj in enumerate(objects, 1):
        if not obj.startswith(f"{i} 0 obj"):
            obj = f"{i} 0 obj\n" + obj.split(" 0 obj\n", 1)[-1]
        numbered.append(obj)

    body  = "%PDF-1.4\n"
    offsets: List[int] = []
    for obj in numbered:
        offsets.append(len(body))
        body += obj + "\n"

    xref_offset = len(body)
    xref  = f"xref\n0 {len(numbered)+1}\n0000000000 65535 f \n"
    for off in offsets:
        xref += f"{off:010d} 00000 n \n"

    trailer = (
        f"trailer\n<< /Size {len(numbered)+1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    )

    with open(pdf_path, "w", errors="replace") as f:
        f.write(body + xref + trailer)