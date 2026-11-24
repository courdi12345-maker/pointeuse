"""
Réglages de Pointage Max.

Les valeurs sensibles ou propres à chaque installation se règlent par variables
d'environnement (voir README.md) :

    POINTAGE_DEBUG=1            mode développement (jamais en production)
    POINTAGE_HOSTS=192.168.1.20,pointage.local
    POINTAGE_TZ=Africa/Casablanca
    POINTAGE_HTTPS=1            si le site est servi en HTTPS (cookies sécurisés)
    POINTAGE_DATA_DIR=/data     dossier des données (base, photos, sauvegardes, clé secrète),
                                à placer sur un disque persistant pour la version en ligne
    POINTAGE_EN_LIGNE=1         version hébergée sur Internet (sécurité renforcée, voir EN_LIGNE.md)
"""

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Dossier des données propres à l'installation. Par défaut le dossier du logiciel (usage local) ;
# en ligne, un disque persistant (ex. /data) pour que rien ne soit perdu à chaque mise à jour.
DATA_DIR = Path(os.environ.get("POINTAGE_DATA_DIR", BASE_DIR))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Les migrations de « pointages » ne sont pas dans Git : elles sont créées sur chaque installation.
# Quand les données sont sur un disque séparé (version en ligne), on les y range aussi, sinon elles
# seraient perdues à chaque mise à jour du serveur et la base ne suivrait plus le code.
MIGRATION_MODULES = {}
if DATA_DIR.resolve() != BASE_DIR.resolve():
    import sys
    _paquet = DATA_DIR / "migrations_pointages"
    _paquet.mkdir(exist_ok=True)
    (_paquet / "__init__.py").touch()
    if str(DATA_DIR) not in sys.path:
        sys.path.append(str(DATA_DIR))
    MIGRATION_MODULES["pointages"] = "migrations_pointages"


def _env_bool(nom, defaut="0"):
    return os.environ.get(nom, defaut).lower() in ("1", "true", "oui", "yes")


def _cle_secrete():
    """Clé lue dans l'environnement, sinon dans secret_key.txt (créé au premier lancement, hors Git)."""
    if os.environ.get("POINTAGE_SECRET_KEY"):
        return os.environ["POINTAGE_SECRET_KEY"]
    fichier = DATA_DIR / "secret_key.txt"
    if not fichier.exists():
        fichier.write_text(secrets.token_urlsafe(50))
        fichier.chmod(0o600)
    return fichier.read_text().strip()


SECRET_KEY = _cle_secrete()

EN_LIGNE = _env_bool("POINTAGE_EN_LIGNE")
DEBUG = _env_bool("POINTAGE_DEBUG") and not EN_LIGNE

ALLOWED_HOSTS = [h.strip() for h in os.environ.get("POINTAGE_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
if os.environ.get("POINTAGE_HOSTS", "") == "*":
    ALLOWED_HOSTS = ["*"]
# Hébergeurs qui donnent eux-mêmes l'adresse publique du site (Render, Railway).
for _var in ("RENDER_EXTERNAL_HOSTNAME", "RAILWAY_PUBLIC_DOMAIN"):
    if os.environ.get(_var) and os.environ[_var] not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(os.environ[_var])


# --- Réglages métier ---------------------------------------------------------
# Valeurs par défaut pour le Maroc. Pour la Belgique par exemple :
# DEVISE "€", HEURES_MENSUELLES 164.67 (38 h/sem.), JOURS_REPOS [5, 6], CONGE_ANNUEL_JOURS 20.

POINTAGE_MAX = {
    "NOM": "Pointage Max",
    "DEVISE": os.environ.get("POINTAGE_DEVISE", "DH"),
    "HEURES_MENSUELLES": float(os.environ.get("POINTAGE_HEURES_MENSUELLES", "191")),  # 44 h/semaine
    "HEURES_PAR_JOUR": float(os.environ.get("POINTAGE_HEURES_PAR_JOUR", "8")),
    "JOURS_REPOS": [int(j) for j in os.environ.get("POINTAGE_JOURS_REPOS", "6").split(",") if j != ""],  # 0=lundi … 6=dimanche
    "CONGE_ANNUEL_JOURS": int(os.environ.get("POINTAGE_CONGE_ANNUEL", "18")),  # 1,5 jour par mois
    "CONGE_REPORT_ANNEES": int(os.environ.get("POINTAGE_CONGE_REPORT", "2")),  # reliquat utilisable 2 ans de plus
    "HEURE_DEBUT": os.environ.get("POINTAGE_HEURE_DEBUT", "08:00"),
    "TOLERANCE_RETARD_MINUTES": int(os.environ.get("POINTAGE_TOLERANCE_RETARD", "10")),
    "DELAI_MIN_MINUTES": 1,  # délai minimum entre une arrivée et une sortie
    "SAUVEGARDES_DIR": os.environ.get("POINTAGE_SAUVEGARDES_DIR", str(DATA_DIR / "sauvegardes")),
    "SAUVEGARDES_A_GARDER": int(os.environ.get("POINTAGE_SAUVEGARDES_A_GARDER", "30")),
    # Fiche de paie : retenues salariales (Maroc, barème 2025). Montants INDICATIFS : faites-les valider
    # par votre comptable et mettez ces valeurs à jour à chaque loi de finances.
    "PAIE": {
        "CNSS_TAUX": 0.0448, "CNSS_PLAFOND_MENSUEL": 6000,
        "AMO_TAUX": 0.0226,
        "FRAIS_PRO_SEUIL_ANNUEL": 78000, "FRAIS_PRO_TAUX_BAS": 0.35, "FRAIS_PRO_TAUX_HAUT": 0.25,
        "FRAIS_PRO_PLAFOND_ANNUEL": 35000,
        # (jusqu'à ce revenu net imposable annuel, taux, somme à déduire)
        "IR_BAREME_ANNUEL": [(40000, 0, 0), (60000, 0.10, 4000), (80000, 0.20, 10000),
                             (100000, 0.30, 18000), (180000, 0.34, 22000), (None, 0.37, 27400)],
        "IR_DEDUCTION_PAR_PERSONNE_ANNUELLE": 500, "IR_PERSONNES_MAX": 6,
        "ACTIVE": os.environ.get("POINTAGE_RETENUES", "1") == "1",
    },
}


# --- Application ---------------------------------------------------------------

INSTALLED_APPS = [
    'pointages',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

MIDDLEWARE = [
    'pointages.services.SanteMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'pointages.services.UtilisateurCourantMiddleware',
    'pointages.services.EntetesSecuriteMiddleware',
]

ROOT_URLCONF = 'pointeuse.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'pointages.context_processors.pointage_max',
            ],
        },
    },
]

WSGI_APPLICATION = 'pointeuse.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': DATA_DIR / 'db.sqlite3',
        'OPTIONS': {'timeout': 20},
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 6}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "accueil"
LOGOUT_REDIRECT_URL = "login"


# --- Langue et heure -------------------------------------------------------------

LANGUAGE_CODE = 'fr'
TIME_ZONE = os.environ.get("POINTAGE_TZ", "Africa/Casablanca")
USE_I18N = True
USE_TZ = True


# --- Fichiers ---------------------------------------------------------------------

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = DATA_DIR / 'media'
FILE_UPLOAD_PERMISSIONS = 0o640
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'


# --- Sécurité ----------------------------------------------------------------------

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 12 * 3600
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
CSRF_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True

if _env_bool("POINTAGE_HTTPS") or EN_LIGNE:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    CSRF_TRUSTED_ORIGINS = ["https://%s" % h for h in ALLOWED_HOSTS if h != "*"]

if EN_LIGNE:
    # Le site est sur Internet : HTTPS obligatoire et retenu par le navigateur.
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    # Mots de passe plus solides que pour un usage local.
    AUTH_PASSWORD_VALIDATORS[1]["OPTIONS"]["min_length"] = 10

# Blocage des connexions après plusieurs échecs (cache partagé entre les processus).
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": str(DATA_DIR / "cache"),
    }
}
CONNEXION_ESSAIS_MAX = int(os.environ.get("POINTAGE_ESSAIS_MAX", "5"))
CONNEXION_BLOCAGE_MINUTES = int(os.environ.get("POINTAGE_BLOCAGE_MINUTES", "15"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "django": {"handlers": ["console"], "level": "WARNING"},
        "pointages": {"handlers": ["console"], "level": "INFO"},
    },
}
