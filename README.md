# Cloneur de disque — Borne autonome (Debian 13)

Application de clonage bit-à-bit USB-vers-USB, pensée pour tourner en
kiosque sur un PC standard sous Debian 13 (le support Raspberry Pi n'est
plus nécessaire).

## Deux variantes du code

| Dossier            | Utilisé pour                          | Panneau Administration |
|---------------------|----------------------------------------|--------------------------|
| `code/`             | Mode **Live** (clé USB / démo rapide)  | **Accès libre**, sans mot de passe |
| `code_installer/`   | Mode **Installé** (borne définitive)   | **Protégé par mot de passe** (défini au premier accès) |

Les deux dossiers contiennent exactement les mêmes fichiers ; seul
`admin_interface.py` diffère (présence ou non de la vérification du mot de
passe). Tout le reste — détection des ports, clonage, logs, PDF — est
identique dans les deux variantes.

## Architecture (fichiers communs aux deux dossiers)

| Fichier                | Rôle |
|-------------------------|------|
| `main.py`               | Point d'entrée, vérifie les droits root, lance la GUI |
| `gui_interface.py`      | Fenêtre principale : détection des disques, lancement du clonage, progression |
| `admin_interface.py`    | Panneau admin : config des ports, PDF, purge logs, arrêt système (± mot de passe selon le dossier) |
| `clone.py`              | Pilotage du sous-processus `dd`, calcul de progression, annulation, vérification |
| `port_detector.py`      | Assistant de détection de port physique (débrancher/brancher) |
| `config_manager.py`     | Configuration persistante (`/etc/disk_cloner/config.json`) |
| `log_handler.py`        | Journalisation avec rotation + génération de rapports PDF |
| `utils.py`              | Détection des disques USB, résolution des ports via udev (`ID_PATH`) |

## Installation sur Debian 13

Deux façons de déployer :

1. **Via l'ISO dual-boot** (`forgeIsoCloner64.sh`) — solution recommandée pour
   une vraie borne : boot Live (mode `code/`, admin libre) ou installation
   définitive sur le disque interne (mode `code_installer/`, admin protégé).
   Voir la section suivante.
2. **Installation manuelle** d'une seule variante sur un Debian 13 existant,
   via systemd (ci-dessous). Pour une borne définitive, utilisez plutôt le
   contenu de `code_installer/` (admin protégé par mot de passe) :

```bash
sudo apt update
sudo apt install -y python3 python3-tk udev util-linux coreutils

sudo mkdir -p /opt/disk-cloner
sudo cp code_installer/*.py /opt/disk-cloner/
sudo cp disk-cloner.service /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable disk-cloner.service
```

Aucune dépendance Python externe n'est requise : uniquement la bibliothèque
standard (`tkinter`, `subprocess`, `threading`, `json`, `hashlib`...) et les
utilitaires système `dd`, `lsblk`, `udevadm`, `blockdev`, `umount`, `cmp`.

## Premier démarrage

1. Lancez l'application (`sudo python3 main.py` ou via le service systemd).
2. Ouvrez **Administration** (aucun mot de passe n'existe encore : vous serez
   invité à en créer un).
3. Dans le panneau admin, cliquez sur **Détecter / reconfigurer le port
   source** : débranchez tout disque de test, puis branchez un disque sur
   le port physique que vous voulez utiliser comme port SOURCE. La détection
   est automatique (comparaison des périphériques USB avant/après branchement,
   puis lecture de l'identifiant udev stable `ID_PATH` du port).
4. Répétez l'opération pour le port DESTINATION (branchez un disque de test
   sur l'autre port du hub).
5. Ces ports restent enregistrés définitivement : peu importe quel disque
   sera branché ensuite, l'application saura toujours lequel est « source »
   et lequel est « destination » d'après le port physique utilisé, pas
   d'après la lettre `/dev/sdX` (qui, elle, peut changer d'un démarrage à
   l'autre).

## Utilisation quotidienne

1. Branchez le disque à copier sur le port SOURCE, et un disque de capacité
   suffisante sur le port DESTINATION.
2. L'application détecte automatiquement les deux disques (modèle, taille,
   numéro de série) toutes les 2 secondes.
3. Le bouton **Démarrer le clonage** ne s'active que si :
   - un disque est présent sur chaque port,
   - le disque de destination est au moins aussi grand que la source.
4. Une double confirmation est demandée avant le clonage (destructif pour
   la destination), y compris la saisie du mot « EFFACER ».
5. La progression (pourcentage, vitesse, ETA) s'affiche en direct, avec un
   bouton **Annuler** pour interrompre proprement le clonage.
6. En option (panneau admin), une vérification bit-à-bit peut être activée
   après chaque clonage.

## Matériel recommandé

- PC ou mini-PC sous Debian 13, avec au moins 2 ports USB dédiés au hub de
  clonage (idéalement un **hub USB alimenté** pour les disques 3,5").
- 2 adaptateurs/boîtiers USB-SATA (ou NVMe selon vos besoins).
- Écran tactile ou clavier/souris pour l'interaction avec la borne.

## Sécurité et bonnes pratiques

- L'application doit être lancée en root (accès direct aux périphériques
  bloc `/dev/sdX`).
- Toutes les partitions montées des deux disques sont démontées avant le
  clonage.
- Les logs sont conservés dans `/var/log/disk_cloner/` avec rotation
  automatique (10 Mo par fichier, 10 fichiers tournés conservés).
- Les rapports PDF (session courante ou historique complet) sont générés
  dans `/var/log/disk_cloner/pdf/`, exportables depuis le panneau admin.