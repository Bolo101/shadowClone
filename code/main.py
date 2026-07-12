#!/usr/bin/env python3
"""
main.py – Point d'entrée du cloneur de disque (borne autonome, Debian 13).

Usage :
    sudo python3 main.py
"""
import os
import sys

from gui_interface import run_gui_mode


def main() -> None:
    if os.geteuid() != 0:
        print("Ce programme doit être exécuté en tant que root (accès direct aux disques).")
        sys.exit(1)

    run_gui_mode()


if __name__ == "__main__":
    main()