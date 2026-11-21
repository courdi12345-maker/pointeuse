"""Sauvegarde et restauration de Pointage Max (base de données + photos et documents).

Une sauvegarde est un fichier .zip contenant :
  - db.sqlite3      copie cohérente de la base (API de sauvegarde SQLite, sûre même en cours d'utilisation)
  - media/...       photos et pièces d'identité
  - sauvegarde.json date, version et quelques compteurs
"""
import json
import re
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.db import connections
from django.utils import timezone

NOM_VALIDE = re.compile(r"^pointage-max-\d{8}-\d{6}(-[a-z-]+)?\.zip$")
TABLES_REQUISES = {"pointages_personne", "pointages_pointage", "auth_user"}


class SauvegardeInvalide(Exception):
    pass


def dossier():
    d = Path(settings.POINTAGE_MAX["SAUVEGARDES_DIR"])
    d.mkdir(parents=True, exist_ok=True)
    return d


def _connexion_django():
    """Connexion SQLite brute utilisée par Django (fichier ou base de test)."""
    con = connections["default"]
    con.ensure_connection()
    return con.connection


def _copier_base(vers):
    dst = sqlite3.connect(vers)
    try:
        _connexion_django().backup(dst)
    finally:
        dst.close()


def creer(motif="manuelle"):
    """Crée une sauvegarde et renvoie son chemin. Supprime les plus anciennes au-delà de la limite."""
    nom = "pointage-max-%s-%s.zip" % (timezone.localtime().strftime("%Y%m%d-%H%M%S"), motif)
    chemin = dossier() / nom
    media = Path(settings.MEDIA_ROOT)
    with tempfile.TemporaryDirectory() as tmp:
        copie = Path(tmp) / "db.sqlite3"
        _copier_base(copie)
        infos = _infos_base(copie)
        infos.update({"date": timezone.localtime().isoformat(), "motif": motif, "application": "Pointage Max"})
        partiel = chemin.with_suffix(".part")
        with zipfile.ZipFile(partiel, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(copie, "db.sqlite3")
            if media.exists():
                for f in sorted(media.rglob("*")):
                    if f.is_file():
                        z.write(f, "media/" + f.relative_to(media).as_posix())
            z.writestr("sauvegarde.json", json.dumps(infos, ensure_ascii=False, indent=2))
        partiel.rename(chemin)  # le fichier n'apparaît qu'une fois complet
    _rotation()
    return chemin


def _rotation():
    garder = settings.POINTAGE_MAX["SAUVEGARDES_A_GARDER"]
    fichiers = sorted(dossier().glob("pointage-max-*.zip"), key=lambda f: f.name, reverse=True)
    for vieux in fichiers[garder:]:
        vieux.unlink(missing_ok=True)


def _infos_base(chemin):
    try:
        con = sqlite3.connect("file:%s?mode=ro" % chemin, uri=True)
        try:
            if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise SauvegardeInvalide("la base de données de la sauvegarde est endommagée")
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not TABLES_REQUISES <= tables:
                raise SauvegardeInvalide("ce fichier n'est pas une sauvegarde de Pointage Max")
            return {
                "employes": con.execute("SELECT COUNT(*) FROM pointages_personne").fetchone()[0],
                "pointages": con.execute("SELECT COUNT(*) FROM pointages_pointage").fetchone()[0],
            }
        finally:
            con.close()
    except sqlite3.DatabaseError as e:
        raise SauvegardeInvalide("base de données illisible (%s)" % e)


def lister():
    res = []
    for f in sorted(dossier().glob("pointage-max-*.zip"), key=lambda f: f.name, reverse=True):
        st = f.stat()
        res.append({"nom": f.name, "taille": st.st_size,
                    "date": timezone.make_aware(datetime.strptime(f.name[13:28], "%Y%m%d-%H%M%S")),
                    "motif": f.stem[29:] or "manuelle"})
    return res


def chemin_existant(nom):
    """Chemin d'une sauvegarde du dossier, en refusant tout nom suspect."""
    if not NOM_VALIDE.match(nom or ""):
        raise SauvegardeInvalide("nom de sauvegarde invalide")
    chemin = dossier() / nom
    if not chemin.is_file():
        raise SauvegardeInvalide("sauvegarde introuvable")
    return chemin


def _membres_media(z):
    membres = []
    for info in z.infolist():
        nom = info.filename
        if nom in ("db.sqlite3", "sauvegarde.json") or nom.endswith("/"):
            continue
        p = PurePosixPath(nom)
        if p.is_absolute() or ".." in p.parts or p.parts[0] != "media" or "\\" in nom:
            raise SauvegardeInvalide("le fichier contient un chemin interdit : %s" % nom[:80])
        membres.append(info)
    return membres


def verifier(fichier):
    """Vérifie une sauvegarde (chemin ou fichier envoyé) et renvoie ses informations."""
    try:
        with zipfile.ZipFile(fichier) as z:
            if "db.sqlite3" not in z.namelist():
                raise SauvegardeInvalide("le fichier ne contient pas de base de données")
            membres = _membres_media(z)
            with tempfile.TemporaryDirectory() as tmp:
                z.extract("db.sqlite3", tmp)
                infos = _infos_base(Path(tmp) / "db.sqlite3")
            infos["fichiers"] = len(membres)
            return infos
    except zipfile.BadZipFile:
        raise SauvegardeInvalide("ce n'est pas un fichier .zip valide")


def restaurer(fichier):
    """Remplace la base et les fichiers par ceux de la sauvegarde.

    Une sauvegarde « avant-restauration » de l'état actuel est faite d'abord.
    Renvoie (infos de la sauvegarde restaurée, chemin de la sauvegarde de sécurité).
    """
    infos = verifier(fichier)
    if hasattr(fichier, "seek"):
        fichier.seek(0)
    securite = creer("avant-restauration")
    media = Path(settings.MEDIA_ROOT)
    with zipfile.ZipFile(fichier) as z, tempfile.TemporaryDirectory() as tmp:
        z.extract("db.sqlite3", tmp)
        src = sqlite3.connect(Path(tmp) / "db.sqlite3")
        try:
            src.backup(_connexion_django())  # remplace le contenu de la base en une seule opération
        finally:
            src.close()
        # Fichiers : on remplace le dossier media entier
        nouveau = Path(tmp) / "media_nouveau"
        for info in _membres_media(z):
            cible = nouveau / PurePosixPath(info.filename).relative_to("media")
            cible.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as s, open(cible, "wb") as d:
                shutil.copyfileobj(s, d)
        if media.exists():
            shutil.rmtree(media)
        if nouveau.exists():
            shutil.copytree(nouveau, media)
        else:
            media.mkdir(parents=True, exist_ok=True)
    return infos, securite
