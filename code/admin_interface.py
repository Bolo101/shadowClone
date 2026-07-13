"""
admin_interface.py - Interface d'administration (VERSION LIVE, sans mot de passe).

Fonctionnalites :
  * Configuration des ports physiques source / destination (assistant de
    detection : debrancher puis brancher un disque de test sur le port vise)
  * Generation PDF : rapport de session / logs complets
  * Purge des logs
  * Reglages de clonage (taille de bloc, verification post-clonage)
  * Redemarrer / Eteindre

Cette fenetre s'ouvre en plein ecran (comme la fenetre principale) : touche
F11 pour basculer, Echap pour fermer le panneau.
"""
from __future__ import annotations

import subprocess
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Optional

import config_manager
from log_handler import (
    generate_log_file_pdf,
    generate_session_pdf,
    log_error,
    log_info,
    log_application_exit,
    purge_logs,
)
from port_detector import DetectionCancelled, DetectionTimeout, run_detection_wizard
from utils import DiskInfo

# ── Palette (alignee sur le theme sombre de gui_interface.py) ───────────────
_BG          = "#0b1220"
_SURFACE     = "#14233c"
_SURFACE2    = "#1a2d4c"
_SURFACE3    = "#21375c"
_BORDER      = "#1c3556"
_TEXT        = "#edf4ff"
_TEXT_DIM    = "#9bb4d1"
_HEADER_BG   = "#1e3a5f"
_HEADER_FG   = "#ffffff"
_ACCENT2     = "#39a0ff"
_BTN_ACTION  = "#2980b9"
_BTN_ACT_A   = "#3f9ade"
_BTN_DANGER  = "#e74c3c"
_BTN_DNG_A   = "#ff6b5c"
_BTN_SYS     = "#3d4f66"
_BTN_SYS_A   = "#4d6280"
_BTN_CLOSE   = "#27ae60"
_BTN_CLOSE_A = "#31d67a"


def _apply_admin_styles(root: tk.Widget) -> None:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure("TFrame", background=_BG)
    style.configure("TLabel", background=_BG, foreground=_TEXT, font=("Helvetica", 10))
    style.configure("TEntry", fieldbackground=_SURFACE2, foreground=_TEXT,
                    selectbackground=_ACCENT2, selectforeground="white",
                    insertcolor=_TEXT, bordercolor=_BORDER, font=("Helvetica", 10))
    style.configure("TCheckbutton", background=_BG, foreground=_TEXT, font=("Helvetica", 10))
    style.map("TCheckbutton", background=[("active", _BG)], foreground=[("active", _TEXT)])

    style.configure("TCombobox", fieldbackground=_SURFACE2, background=_SURFACE2,
                    foreground=_TEXT, arrowcolor=_TEXT, bordercolor=_BORDER)
    style.map("TCombobox",
              fieldbackground=[("readonly", _SURFACE2)],
              foreground=[("readonly", _TEXT)],
              background=[("readonly", _SURFACE2)])
    root.option_add("*TCombobox*Listbox.background", _SURFACE2)
    root.option_add("*TCombobox*Listbox.foreground", _TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", _ACCENT2)
    root.option_add("*TCombobox*Listbox.selectForeground", "white")

    style.configure("TLabelframe", background=_BG, bordercolor=_BORDER,
                    darkcolor=_BORDER, lightcolor=_BORDER, relief="groove")
    style.configure("TLabelframe.Label", background=_BG, foreground=_ACCENT2,
                    font=("Helvetica", 10, "bold"))

    style.configure("TSeparator", background=_BORDER)

    style.configure("TProgressbar", troughcolor=_SURFACE2, background=_ACCENT2,
                    bordercolor=_SURFACE2, lightcolor=_ACCENT2, darkcolor=_ACCENT2)

    style.configure("AdminHeader.TFrame", background=_HEADER_BG)
    style.configure("AdminHeader.TLabel", background=_HEADER_BG, foreground=_HEADER_FG,
                    font=("Helvetica", 15, "bold"))
    style.configure("TButton", background=_BTN_SYS, foreground="white",
                    font=("Helvetica", 10), borderwidth=0, padding=(10, 6), relief="flat")
    style.map("TButton", background=[("active", _BTN_SYS_A)])

    for name, bg, bg_a in [
        ("Action", _BTN_ACTION, _BTN_ACT_A),
        ("Danger", _BTN_DANGER, _BTN_DNG_A),
        ("Sys", _BTN_SYS, _BTN_SYS_A),
        ("Close", _BTN_CLOSE, _BTN_CLOSE_A),
    ]:
        style.configure(f"Admin{name}.TButton", foreground="white", background=bg,
                        font=("Helvetica", 10), borderwidth=0, padding=(12, 7), relief="flat")
        style.map(f"Admin{name}.TButton", background=[("active", bg_a)])


class PortDetectionDialog(tk.Toplevel):
    """
    Fenetre modale guidant l'utilisateur pas a pas dans la detection d'un
    port physique (debrancher -> brancher -> detection automatique).
    Reste une petite boite centree (ce n'est pas la fenetre principale).
    """

    def __init__(self, parent: tk.Widget, port_label: str) -> None:
        super().__init__(parent)
        self.title(f"Detection du port {port_label}")
        self.resizable(False, False)
        self.grab_set()
        self.configure(bg=_BG)
        _apply_admin_styles(self)

        self.result: Optional[DiskInfo] = None
        self._cancelled = False

        header = ttk.Frame(self, style="AdminHeader.TFrame", padding=(20, 12))
        header.pack(fill=tk.X)
        ttk.Label(header, text=f"Configuration du port {port_label}",
                  style="AdminHeader.TLabel").pack()

        body = ttk.Frame(self, padding=(24, 16))
        body.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            body,
            text=(
                "1. Debranchez tout disque de test actuellement branche.\n"
                "2. Une fois cette fenetre prete, branchez UN disque quelconque "
                f"sur le port physique que vous souhaitez affecter a « {port_label} ».\n"
                "3. La detection est automatique : ne branchez rien sur un autre port "
                "pendant l'operation."
            ),
            wraplength=420, justify="left",
        ).pack(anchor="w", pady=(0, 14))

        self._status_var = tk.StringVar(value="Preparation...")
        ttk.Label(body, textvariable=self._status_var, font=("Helvetica", 10, "bold")).pack(anchor="w")

        self._progress = ttk.Progressbar(body, mode="indeterminate", length=380)
        self._progress.pack(fill=tk.X, pady=(10, 16))
        self._progress.start(12)

        btn_row = ttk.Frame(body)
        btn_row.pack(fill=tk.X)
        ttk.Button(btn_row, text="Annuler", command=self._cancel).pack(side=tk.RIGHT)

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

        threading.Thread(target=self._run_wizard, daemon=True).start()
        self.wait_window(self)

    def _set_status(self, text: str) -> None:
        self.after(0, lambda: self._status_var.set(text))

    def _run_wizard(self) -> None:
        try:
            disk = run_detection_wizard(
                timeout=90,
                cancel_check=lambda: self._cancelled,
                status_cb=self._set_status,
            )
            self.after(0, lambda: self._on_success(disk))
        except DetectionTimeout:
            self.after(0, lambda: self._on_failure(
                "Aucun disque detecte dans le delai imparti (90 s). "
                "Verifiez le branchement et reessayez."
            ))
        except DetectionCancelled:
            self.after(0, self.destroy)
        except Exception as e:
            self.after(0, lambda: self._on_failure(f"Erreur pendant la detection : {e}"))

    def _on_success(self, disk: DiskInfo) -> None:
        self._progress.stop()
        self.result = disk
        messagebox.showinfo(
            "Port detecte",
            f"Disque detecte avec succes :\n\n{disk.model} ({disk.size_human})\n"
            f"Serie : {disk.serial}\nChemin : {disk.path}",
            parent=self,
        )
        self.destroy()

    def _on_failure(self, message: str) -> None:
        self._progress.stop()
        messagebox.showerror("Echec de la detection", message, parent=self)
        self.destroy()

    def _cancel(self) -> None:
        self._cancelled = True
        self.destroy()


class AdminPanel(tk.Toplevel):
    def __init__(self, parent: tk.Widget, on_ports_changed: Optional[Callable[[], None]] = None) -> None:
        super().__init__(parent)
        self.title("Administration - Cloneur de disque (mode Live)")
        self.configure(bg=_BG)
        self.resizable(True, True)
        self._parent = parent
        self._on_ports_changed = on_ports_changed
        _apply_admin_styles(self)

        # ── Plein ecran (comme la fenetre principale) ────────────────────
        self._fullscreen = True
        self._apply_fullscreen(self._fullscreen)
        self.bind('<F11>', self._toggle_fullscreen)
        self.bind('<Escape>', lambda e: self.destroy())
        self.after(150, lambda: self._apply_fullscreen(self._fullscreen))

        header = ttk.Frame(self, style="AdminHeader.TFrame", padding=(20, 14))
        header.pack(fill=tk.X)
        ttk.Label(header, text="Panneau d'administration - Mode Live (acces libre)",
                  style="AdminHeader.TLabel").pack()

        # Zone de contenu centree, largeur confortable, sur fond plein ecran
        outer = ttk.Frame(self)
        outer.pack(fill=tk.BOTH, expand=True)
        body = ttk.Frame(outer, padding=(20, 16))
        body.place(relx=0.5, rely=0.0, anchor="n", width=680)

        # -- Ports --------------------------------------------------------
        ports_frame = ttk.LabelFrame(body, text="Ports physiques", padding=(14, 10))
        ports_frame.pack(fill=tk.X, pady=(0, 14))

        self._source_status_var = tk.StringVar()
        self._dest_status_var = tk.StringVar()
        self._refresh_port_labels()

        src_row = ttk.Frame(ports_frame)
        src_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(src_row, text="Port SOURCE :", font=("Helvetica", 10, "bold")).pack(anchor="w")
        ttk.Label(src_row, textvariable=self._source_status_var, wraplength=600).pack(anchor="w", pady=(2, 6))
        ttk.Button(src_row, text="Detecter / reconfigurer le port source",
                   style="AdminAction.TButton",
                   command=lambda: self._detect_port("source")).pack(anchor="w")

        ttk.Separator(ports_frame).pack(fill=tk.X, pady=8)

        dst_row = ttk.Frame(ports_frame)
        dst_row.pack(fill=tk.X)
        ttk.Label(dst_row, text="Port DESTINATION :", font=("Helvetica", 10, "bold")).pack(anchor="w")
        ttk.Label(dst_row, textvariable=self._dest_status_var, wraplength=600).pack(anchor="w", pady=(2, 6))
        ttk.Button(dst_row, text="Detecter / reconfigurer le port destination",
                   style="AdminAction.TButton",
                   command=lambda: self._detect_port("dest")).pack(anchor="w")

        # -- Parametres de clonage -----------------------------------------
        settings_frame = ttk.LabelFrame(body, text="Parametres de clonage", padding=(14, 10))
        settings_frame.pack(fill=tk.X, pady=(0, 14))

        bs_row = ttk.Frame(settings_frame)
        bs_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(bs_row, text="Taille de bloc dd :").pack(side=tk.LEFT)
        self._block_size_var = tk.StringVar(value=config_manager.get_block_size())
        bs_combo = ttk.Combobox(bs_row, textvariable=self._block_size_var, width=8,
                                values=["1M", "4M", "8M", "16M", "32M"], state="readonly")
        bs_combo.pack(side=tk.LEFT, padx=(8, 0))
        bs_combo.bind("<<ComboboxSelected>>", lambda e: config_manager.set_block_size(self._block_size_var.get()))

        self._verify_var = tk.BooleanVar(value=config_manager.get_verify_after_clone())
        ttk.Checkbutton(
            settings_frame, text="Verifier l'integrite apres chaque clonage (plus lent)",
            variable=self._verify_var,
            command=lambda: config_manager.set_verify_after_clone(self._verify_var.get()),
        ).pack(anchor="w")

        # -- Journaux -------------------------------------------------------
        logs_frame = ttk.LabelFrame(body, text="Journaux", padding=(14, 10))
        logs_frame.pack(fill=tk.X, pady=(0, 14))
        logs_btns = ttk.Frame(logs_frame)
        logs_btns.pack(fill=tk.X)
        ttk.Button(logs_btns, text="PDF session courante", style="AdminAction.TButton",
                   command=self._export_session_pdf).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(logs_btns, text="PDF logs complets", style="AdminAction.TButton",
                   command=self._export_full_pdf).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(logs_btns, text="Purger les logs", style="AdminDanger.TButton",
                   command=self._purge_logs).pack(side=tk.LEFT)

        # -- Systeme ---------------------------------------------------------
        sys_frame = ttk.LabelFrame(body, text="Systeme", padding=(14, 10))
        sys_frame.pack(fill=tk.X)
        sys_btns = ttk.Frame(sys_frame)
        sys_btns.pack(fill=tk.X)
        ttk.Button(sys_btns, text="Redemarrer", style="AdminSys.TButton",
                   command=self._reboot).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(sys_btns, text="Eteindre", style="AdminSys.TButton",
                   command=self._shutdown).pack(side=tk.LEFT, padx=(0, 8))

        close_row = ttk.Frame(body)
        close_row.pack(fill=tk.X, pady=(14, 0))
        ttk.Label(close_row, text="Echap ferme ce panneau  ·  F11 bascule le plein ecran",
                  foreground=_TEXT_DIM).pack(side=tk.LEFT)
        ttk.Button(close_row, text="Fermer", command=self.destroy).pack(side=tk.RIGHT)

    # ── Plein ecran ──────────────────────────────────────────────────────
    def _apply_fullscreen(self, enabled: bool) -> None:
        try:
            self.attributes('-fullscreen', enabled)
        except tk.TclError:
            if enabled:
                w = self.winfo_screenwidth()
                h = self.winfo_screenheight()
                self.geometry(f"{w}x{h}+0+0")
            else:
                self.geometry("620x680")

    def _toggle_fullscreen(self, event=None) -> None:
        self._fullscreen = not self._fullscreen
        self._apply_fullscreen(self._fullscreen)

    # -- Ports --------------------------------------------------------------
    def _refresh_port_labels(self) -> None:
        cfg = config_manager.load_config()
        src = cfg.get("source_id_path")
        dst = cfg.get("dest_id_path")
        self._source_status_var.set(
            f"Configure ({cfg.get('source_label') or 'port'} : {src})" if src else "Non configure"
        )
        self._dest_status_var.set(
            f"Configure ({cfg.get('dest_label') or 'port'} : {dst})" if dst else "Non configure"
        )

    def _detect_port(self, which: str) -> None:
        label = "SOURCE" if which == "source" else "DESTINATION"
        dialog = PortDetectionDialog(self, label)
        disk = dialog.result
        if disk is None:
            return

        label_info = f"{disk.model} ({disk.serial})"
        if which == "source":
            config_manager.set_source_id_path(disk.id_path, label_info)
            log_info(f"Port source configure : {disk.id_path} ({label_info})")
        else:
            config_manager.set_dest_id_path(disk.id_path, label_info)
            log_info(f"Port destination configure : {disk.id_path} ({label_info})")

        self._refresh_port_labels()
        if self._on_ports_changed:
            self._on_ports_changed()

    # -- Journaux -------------------------------------------------------------
    def _export_session_pdf(self) -> None:
        try:
            path = generate_session_pdf()
            messagebox.showinfo("PDF genere", f"Rapport genere :\n{path}", parent=self)
        except ValueError as e:
            messagebox.showwarning("Aucune donnee", str(e), parent=self)
        except OSError as e:
            log_error(f"Erreur generation PDF session : {e}")
            messagebox.showerror("Erreur", f"Impossible de generer le PDF : {e}", parent=self)

    def _export_full_pdf(self) -> None:
        try:
            path = generate_log_file_pdf()
            messagebox.showinfo("PDF genere", f"Rapport genere :\n{path}", parent=self)
        except ValueError as e:
            messagebox.showwarning("Aucune donnee", str(e), parent=self)
        except OSError as e:
            log_error(f"Erreur generation PDF logs : {e}")
            messagebox.showerror("Erreur", f"Impossible de generer le PDF : {e}", parent=self)

    def _purge_logs(self) -> None:
        if messagebox.askyesno("Purger les logs", "Supprimer definitivement tous les journaux ?", parent=self):
            purge_logs()
            messagebox.showinfo("Logs purges", "Les journaux ont ete supprimes.", parent=self)

    # -- Systeme ----------------------------------------------------------------
    def _reboot(self) -> None:
        if messagebox.askyesno("Redemarrer", "Redemarrer la machine maintenant ?", parent=self):
            log_application_exit("Redemarrage systeme (admin live)")
            subprocess.run(["systemctl", "reboot"], check=False)

    def _shutdown(self) -> None:
        if messagebox.askyesno("Eteindre", "Eteindre la machine maintenant ?", parent=self):
            log_application_exit("Extinction systeme (admin live)")
            subprocess.run(["systemctl", "poweroff"], check=False)


def open_admin_panel(parent: tk.Widget, on_ports_changed: Optional[Callable[[], None]] = None) -> None:
    """
    Point d'entree : VERSION LIVE — ouvre directement le panneau
    d'administration, sans authentification.
    """
    AdminPanel(parent, on_ports_changed=on_ports_changed)