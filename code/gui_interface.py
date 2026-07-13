"""
gui_interface.py – Interface graphique principale du cloneur de disque.

Affiche les disques branchés sur les ports "source" et "destination"
(configurés depuis l'interface d'administration), permet de lancer le
clonage bit-à-bit avec suivi en temps réel (pourcentage, vitesse, ETA),
et donne accès au panneau d'administration.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import Optional

import config_manager
from clone import CloneError, CloneJob, CloneProgress, SizeMismatchError, verify_clone
from log_handler import (
    log_error,
    log_info,
    log_clone_operation,
    log_clone_completed,
    log_clone_failed,
    log_clone_process_stopped,
    log_verification_result,
    log_application_exit,
    session_start,
)
from utils import DiskInfo, find_disk_by_id_path, human_size

try:
    from admin_interface import open_admin_panel
except ImportError:
    open_admin_panel = None


class DiskCloneGUI:
    _REFRESH_INTERVAL_MS = 2000

    # Palette (reprise du thème sombre existant)
    _BG = '#0b1220'
    _SURFACE = '#14233c'
    _SURFACE2 = '#1a2d4c'
    _SURFACE3 = '#21375c'
    _BORDER_SOFT = '#1c3556'
    _TEXT = '#edf4ff'
    _TEXT_DIM = '#9bb4d1'
    _TEXT_FAINT = '#6f87a4'
    _ACCENT = '#0b84ff'
    _ACCENT2 = '#39a0ff'
    _DANGER = '#ef5350'
    _WARNING = '#f5b342'
    _SUCCESS = '#21c17a'

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Cloneur de disque - Borne autonome")
        self.root.geometry("1200x760")  # taille de repli si le plein écran échoue
        self.root.minsize(1000, 680)
        self.root.configure(bg=self._BG)
        self._fullscreen = True
        self._apply_fullscreen(self._fullscreen)
        self.root.bind('<F11>', self._toggle_fullscreen)
        self.root.bind('<Escape>', lambda e: None)  # pas de sortie accidentelle du plein écran
        # Certains gestionnaires de fenêtres ignorent -fullscreen tant que la
        # fenêtre n'est pas encore mappée : on le réapplique juste après.
        self.root.after(150, lambda: self._apply_fullscreen(self._fullscreen))

        if os.geteuid() != 0:
            messagebox.showerror("Erreur", "Ce programme doit être exécuté en tant que root.")
            root.destroy()
            sys.exit(1)

        self.source_disk: Optional[DiskInfo] = None
        self.dest_disk: Optional[DiskInfo] = None
        self._clone_job: Optional[CloneJob] = None
        self._cloning = False
        self._start_time = 0.0

        session_start()
        self.root.protocol("WM_DELETE_WINDOW", self._on_quit)

        self._setup_theme()
        self._build_ui()
        self._refresh_disks()
        self.root.after(self._REFRESH_INTERVAL_MS, self._auto_refresh)

    # ── Plein écran (kiosque) ────────────────────────────────────────────
    def _apply_fullscreen(self, enabled: bool) -> None:
        try:
            self.root.attributes('-fullscreen', enabled)
        except tk.TclError:
            # Gestionnaire de fenêtres minimal ne supportant pas l'attribut
            # -fullscreen : on se rabat sur une géométrie couvrant l'écran.
            if enabled:
                w = self.root.winfo_screenwidth()
                h = self.root.winfo_screenheight()
                self.root.geometry(f"{w}x{h}+0+0")
            else:
                self.root.geometry("1200x760")

    def _toggle_fullscreen(self, event=None) -> None:
        self._fullscreen = not self._fullscreen
        self._apply_fullscreen(self._fullscreen)

    # ── Thème ────────────────────────────────────────────────────────────
    def _setup_theme(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass
        style.configure('.', background=self._BG, foreground=self._TEXT, font=('Segoe UI', 10))
        style.configure('TProgressbar', troughcolor=self._SURFACE2,
                        background=self._ACCENT2, bordercolor=self._SURFACE2,
                        lightcolor=self._ACCENT2, darkcolor=self._ACCENT2)

    def _card(self, parent, **pack_kw) -> tk.Frame:
        outer = tk.Frame(parent, bg=self._BORDER_SOFT, bd=0, highlightthickness=0)
        outer.pack(**pack_kw)
        inner = tk.Frame(outer, bg=self._SURFACE, padx=1, pady=1)
        inner.pack(fill=tk.BOTH, expand=True)
        content = tk.Frame(inner, bg=self._SURFACE, padx=14, pady=12)
        content.pack(fill=tk.BOTH, expand=True)
        return content

    def _action_button(self, parent, text, command, bg=None, hover_bg=None,
                       fg='#ffffff', accent=False, state=tk.NORMAL) -> tk.Button:
        bg = bg or self._SURFACE2
        hover_bg = hover_bg or self._SURFACE3
        btn = tk.Button(
            parent, text=text, command=command, bg=bg, fg=fg,
            activebackground=hover_bg, activeforeground=fg,
            font=('Segoe UI', 10, 'bold' if accent else 'normal'),
            bd=0, padx=16, pady=10, cursor='hand2', relief=tk.FLAT,
            highlightthickness=0, state=state,
        )
        btn.bind('<Enter>', lambda e: btn.configure(bg=hover_bg) if btn['state'] != 'disabled' else None)
        btn.bind('<Leave>', lambda e: btn.configure(bg=bg) if btn['state'] != 'disabled' else None)
        return btn

    # ── Construction de l'UI ─────────────────────────────────────────────
    def _build_ui(self) -> None:
        shell = tk.Frame(self.root, bg=self._BG)
        shell.pack(fill=tk.BOTH, expand=True, padx=18, pady=18)

        # En-tête
        header = tk.Frame(shell, bg=self._SURFACE)
        header.pack(fill=tk.X, pady=(0, 14))
        tk.Frame(header, bg=self._ACCENT2, height=3).pack(fill=tk.X, side=tk.TOP)
        header_body = tk.Frame(header, bg=self._SURFACE, padx=18, pady=14)
        header_body.pack(fill=tk.X)

        left_head = tk.Frame(header_body, bg=self._SURFACE)
        left_head.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(left_head, text='Cloneur de disque', bg=self._SURFACE, fg=self._TEXT,
                 font=('Segoe UI', 18, 'bold')).pack(anchor='w')
        tk.Label(left_head, text='Clonage bit-à-bit USB vers USB',
                 bg=self._SURFACE, fg=self._TEXT_DIM, font=('Segoe UI', 9)).pack(anchor='w', pady=(4, 0))

        right_head = tk.Frame(header_body, bg=self._SURFACE)
        right_head.pack(side=tk.RIGHT)
        self._action_button(right_head, 'Administration', self._open_admin,
                            bg='#1e3a5f', hover_bg='#2a5080', accent=True).pack(side=tk.RIGHT)

        # Corps : deux cartes source/destination côte à côte
        disks_row = tk.Frame(shell, bg=self._BG)
        disks_row.pack(fill=tk.X, pady=(0, 10))

        self.source_card = self._card(disks_row, side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))
        self.dest_card = self._card(disks_row, side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0))

        self._source_widgets = self._build_disk_panel(self.source_card, 'SOURCE')
        self._dest_widgets = self._build_disk_panel(self.dest_card, 'DESTINATION')

        # Avertissement destructif
        self.warning_var = tk.StringVar(value='⚠ Le clonage écrase intégralement le disque de destination.')
        tk.Label(shell, textvariable=self.warning_var, bg=self._BG, fg=self._DANGER,
                 font=('Segoe UI', 9, 'bold')).pack(anchor='w', pady=(0, 8))

        # Zone de progression
        progress_card = self._card(shell, fill=tk.X, pady=(0, 10))
        top_row = tk.Frame(progress_card, bg=self._SURFACE)
        top_row.pack(fill=tk.X)
        self._phase_var = tk.StringVar(value='En attente')
        self._percent_var = tk.StringVar(value='0 %')
        tk.Label(top_row, textvariable=self._phase_var, bg=self._SURFACE, fg=self._TEXT,
                 font=('Segoe UI', 10, 'bold')).pack(side=tk.LEFT)
        tk.Label(top_row, textvariable=self._percent_var, bg=self._SURFACE, fg=self._ACCENT2,
                 font=('Segoe UI', 12, 'bold')).pack(side=tk.RIGHT)

        self._progress = ttk.Progressbar(progress_card, orient='horizontal',
                                         mode='determinate', maximum=100)
        self._progress.pack(fill=tk.X, pady=(8, 6))

        detail_row = tk.Frame(progress_card, bg=self._SURFACE)
        detail_row.pack(fill=tk.X)
        self._speed_var = tk.StringVar(value='')
        self._eta_var = tk.StringVar(value='')
        tk.Label(detail_row, textvariable=self._speed_var, bg=self._SURFACE,
                 fg=self._TEXT_DIM, font=('Segoe UI', 9)).pack(side=tk.LEFT)
        tk.Label(detail_row, textvariable=self._eta_var, bg=self._SURFACE,
                 fg=self._TEXT_DIM, font=('Segoe UI', 9)).pack(side=tk.RIGHT)

        # Boutons d'action
        btn_row = tk.Frame(shell, bg=self._BG)
        btn_row.pack(fill=tk.X, pady=(0, 10))
        self.start_btn = self._action_button(
            btn_row, 'Démarrer le clonage', self._on_start_clicked,
            bg=self._ACCENT, hover_bg=self._ACCENT2, accent=True,
        )
        self.start_btn.pack(side=tk.LEFT)
        self.cancel_btn = self._action_button(
            btn_row, 'Annuler', self._on_cancel_clicked,
            bg=self._DANGER, hover_bg='#ff6b66', accent=True, state=tk.DISABLED,
        )
        self.cancel_btn.pack(side=tk.LEFT, padx=(10, 0))

        # Journal (hauteur réduite et fixe : ne remplit plus tout l'espace
        # restant de la fenêtre, ce qui le rendait disproportionné en plein écran)
        log_card = self._card(shell, fill=tk.X, expand=False)
        self.log_text = tk.Text(
            log_card, height=6, wrap=tk.WORD, bg='#0f1a2e', fg=self._TEXT,
            insertbackground=self._TEXT, font=('Consolas', 9), bd=0,
            highlightthickness=0, padx=10, pady=8,
        )
        log_sb = ttk.Scrollbar(log_card, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_sb.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_sb.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_disk_panel(self, parent, title: str) -> dict:
        tk.Label(parent, text=title, bg=self._SURFACE, fg=self._ACCENT2,
                 font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        status_dot = tk.Label(parent, text='●', bg=self._SURFACE, fg=self._DANGER,
                              font=('Segoe UI', 12))
        model_var = tk.StringVar(value='Aucun disque détecté')
        info_var = tk.StringVar(value='')
        port_var = tk.StringVar(value='')

        row = tk.Frame(parent, bg=self._SURFACE)
        row.pack(fill=tk.X, pady=(6, 0))
        status_dot.pack(in_=row, side=tk.LEFT)
        tk.Label(row, textvariable=model_var, bg=self._SURFACE, fg=self._TEXT,
                 font=('Segoe UI', 11, 'bold')).pack(side=tk.LEFT, padx=(6, 0))

        tk.Label(parent, textvariable=info_var, bg=self._SURFACE, fg=self._TEXT_DIM,
                 font=('Segoe UI', 9)).pack(anchor='w', pady=(4, 0))
        tk.Label(parent, textvariable=port_var, bg=self._SURFACE, fg=self._TEXT_FAINT,
                 font=('Segoe UI', 8)).pack(anchor='w', pady=(2, 0))

        return {
            'status_dot': status_dot,
            'model_var': model_var,
            'info_var': info_var,
            'port_var': port_var,
        }

    # ── Rafraîchissement des disques ─────────────────────────────────────
    def _auto_refresh(self) -> None:
        if not self._cloning:
            self._refresh_disks()
        self.root.after(self._REFRESH_INTERVAL_MS, self._auto_refresh)

    def _refresh_disks(self) -> None:
        cfg = config_manager.load_config()
        src_id_path = cfg.get('source_id_path')
        dst_id_path = cfg.get('dest_id_path')

        if not src_id_path or not dst_id_path:
            self.warning_var.set(
                "⚠ Les ports source et destination ne sont pas configurés. "
                "Rendez-vous dans le panneau Administration."
            )

        self.source_disk = find_disk_by_id_path(src_id_path) if src_id_path else None
        self.dest_disk = find_disk_by_id_path(dst_id_path) if dst_id_path else None

        self._update_disk_panel(self._source_widgets, self.source_disk, src_id_path)
        self._update_disk_panel(self._dest_widgets, self.dest_disk, dst_id_path)
        self._update_start_button_state()

    def _update_disk_panel(self, widgets: dict, disk: Optional[DiskInfo], id_path: Optional[str]) -> None:
        if disk is None:
            widgets['status_dot'].configure(fg=self._DANGER)
            widgets['model_var'].set('Aucun disque détecté' if id_path else 'Port non configuré')
            widgets['info_var'].set('')
            widgets['port_var'].set(f"Port : {id_path}" if id_path else 'Configurez ce port dans Administration')
        else:
            widgets['status_dot'].configure(fg=self._SUCCESS)
            widgets['model_var'].set(disk.model)
            widgets['info_var'].set(f"{disk.size_human}  ·  Série : {disk.serial}  ·  {disk.path}")
            widgets['port_var'].set(f"Port : {disk.id_path}")

    def _update_start_button_state(self) -> None:
        if self._cloning:
            return
        ready = (
            self.source_disk is not None
            and self.dest_disk is not None
            and self.dest_disk.size_bytes >= self.source_disk.size_bytes
        )
        self.start_btn.configure(state=tk.NORMAL if ready else tk.DISABLED)

        if self.source_disk and self.dest_disk and self.dest_disk.size_bytes < self.source_disk.size_bytes:
            self.warning_var.set(
                f"⚠ Le disque de destination ({self.dest_disk.size_human}) est plus petit "
                f"que le disque source ({self.source_disk.size_human}). Clonage impossible."
            )
        elif self.source_disk and self.dest_disk:
            self.warning_var.set(
                '⚠ Le clonage écrase intégralement le disque de destination. '
                f"({self.source_disk.path} -> {self.dest_disk.path})"
            )

    # ── Journal GUI (thread-safe) ─────────────────────────────────────────
    def _log(self, message: str) -> None:
        def _insert():
            ts = time.strftime('%Y-%m-%d %H:%M:%S')
            self.log_text.insert(tk.END, f"[{ts}] {message}\n")
            self.log_text.see(tk.END)
        self.root.after(0, _insert)

    # ── Démarrage du clonage ─────────────────────────────────────────────
    def _on_start_clicked(self) -> None:
        if self.source_disk is None or self.dest_disk is None:
            return

        confirm = messagebox.askyesno(
            'Confirmation',
            "Cette opération va EFFACER DÉFINITIVEMENT toutes les données du "
            f"disque de destination :\n\n{self.dest_disk.model} "
            f"({self.dest_disk.size_human}, {self.dest_disk.path})\n\n"
            "Voulez-vous continuer ?",
            icon='warning',
        )
        if not confirm:
            return

        typed = simpledialog.askstring(
            'Confirmation finale',
            'Tapez EFFACER en majuscules pour confirmer le clonage :',
            parent=self.root,
        )
        if typed != 'EFFACER':
            self._log("Clonage annulé : confirmation non saisie correctement.")
            return

        self._start_clone()

    def _start_clone(self) -> None:
        self._cloning = True
        self._clone_job = CloneJob()
        self.start_btn.configure(state=tk.DISABLED)
        self.cancel_btn.configure(state=tk.NORMAL)
        self._phase_var.set('Clonage en cours')
        self._progress.configure(mode='determinate', value=0)
        self._percent_var.set('0 %')
        self._start_time = time.time()

        source_disk = self.source_disk
        dest_disk = self.dest_disk

        log_clone_operation(source_disk.model, dest_disk.model, source_disk.size_bytes)
        self._log(f"Démarrage du clonage : {source_disk.path} -> {dest_disk.path}")

        threading.Thread(
            target=self._clone_worker,
            args=(source_disk, dest_disk),
            daemon=True,
        ).start()

    def _clone_worker(self, source_disk: DiskInfo, dest_disk: DiskInfo) -> None:
        block_size = config_manager.get_block_size()
        try:
            self._clone_job.run(
                source_disk.devname, dest_disk.devname,
                block_size=block_size,
                progress_callback=self._on_progress,
                log_func=self._log,
            )
            log_clone_completed(source_disk.model, dest_disk.model, time.time() - self._start_time)

            if config_manager.get_verify_after_clone():
                self.root.after(0, lambda: self._phase_var.set('Vérification en cours'))
                self.root.after(0, lambda: self._progress.configure(mode='indeterminate'))
                self.root.after(0, self._progress.start)
                success = verify_clone(
                    source_disk.devname, dest_disk.devname,
                    log_func=self._log, cancel_job=self._clone_job,
                )
                log_verification_result(source_disk.model, dest_disk.model, success)
                self.root.after(0, self._progress.stop)
                self.root.after(0, lambda: self._progress.configure(mode='determinate', value=100))
                if not success:
                    self.root.after(0, lambda: self._on_clone_error(
                        "Le clonage s'est terminé mais la vérification a échoué : "
                        "les disques ne sont pas identiques."
                    ))
                    return

            self.root.after(0, self._on_clone_success)

        except SizeMismatchError as e:
            log_clone_failed(source_disk.model, dest_disk.model, str(e))
            self.root.after(0, lambda: self._on_clone_error(str(e)))
        except CloneError as e:
            if self._clone_job.is_cancelled():
                log_clone_process_stopped()
                self.root.after(0, self._on_clone_cancelled)
            else:
                log_clone_failed(source_disk.model, dest_disk.model, str(e))
                self.root.after(0, lambda: self._on_clone_error(str(e)))
        except Exception as e:  # sécurité : ne jamais laisser un thread mourir silencieusement
            log_error(f"Erreur inattendue pendant le clonage : {e}")
            self.root.after(0, lambda: self._on_clone_error(f"Erreur inattendue : {e}"))

    def _on_progress(self, progress: CloneProgress) -> None:
        def _update():
            if progress.percent >= 0:
                self._progress.configure(mode='determinate', value=progress.percent)
                self._percent_var.set(f"{progress.percent:.1f} %")
                self._speed_var.set(f"{progress.speed_mb_s:.1f} Mo/s")
                eta_m, eta_s = divmod(int(progress.eta_seconds), 60)
                self._eta_var.set(f"ETA {eta_m:02d}:{eta_s:02d}")
        self.root.after(0, _update)

    def _on_cancel_clicked(self) -> None:
        if self._clone_job:
            confirm = messagebox.askyesno(
                'Annuler', "Voulez-vous vraiment interrompre le clonage en cours ?"
            )
            if confirm:
                self._clone_job.cancel()
                self._log("Demande d'annulation envoyée...")

    def _reset_clone_state(self) -> None:
        self._cloning = False
        self.cancel_btn.configure(state=tk.DISABLED)
        self._clone_job = None
        self._refresh_disks()

    def _on_clone_success(self) -> None:
        self._phase_var.set('Terminé')
        self._percent_var.set('100 %')
        self._eta_var.set('')
        self._log("Clonage terminé avec succès.")
        self._reset_clone_state()
        messagebox.showinfo('Terminé', 'Le clonage du disque est terminé avec succès.')

    def _on_clone_error(self, message: str) -> None:
        self._phase_var.set('Erreur')
        self._log(f"ERREUR : {message}")
        self._reset_clone_state()
        messagebox.showerror('Erreur de clonage', message)

    def _on_clone_cancelled(self) -> None:
        self._phase_var.set('Annulé')
        self._log("Clonage annulé.")
        self._reset_clone_state()

    # ── Administration ────────────────────────────────────────────────────
    def _open_admin(self) -> None:
        if open_admin_panel is None:
            messagebox.showerror('Erreur', "Le module d'administration est indisponible.")
            return
        open_admin_panel(self.root, on_ports_changed=self._refresh_disks)

    # ── Fermeture ───────────────────────────────────────────────────────────
    def _on_quit(self) -> None:
        if self._cloning:
            if not messagebox.askyesno(
                'Quitter', "Un clonage est en cours. Voulez-vous vraiment quitter ?"
            ):
                return
            if self._clone_job:
                self._clone_job.cancel()
        log_application_exit("Fermeture de la fenêtre")
        self.root.destroy()


def run_gui_mode() -> None:
    try:
        root = tk.Tk()
        DiskCloneGUI(root)
        root.mainloop()
    except tk.TclError as e:
        print(f"Erreur d'initialisation de l'interface graphique : {e}")
        log_error(f"Erreur d'initialisation de l'interface graphique : {e}")
        sys.exit(1)
    except (ImportError, ModuleNotFoundError) as e:
        print(f"Bibliothèque GUI requise indisponible : {e}")
        log_error(f"Bibliothèque GUI requise indisponible : {e}")
        sys.exit(1)
    except OSError as e:
        print(f"Erreur système au démarrage de l'interface graphique : {e}")
        log_error(f"Erreur système au démarrage de l'interface graphique : {e}")
        sys.exit(1)