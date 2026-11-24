# Pointage Max — image pour la version en ligne (Render, Railway, Fly.io, VPS…).
# Les données (base, photos, sauvegardes, clé secrète) vont dans /data : montez-y un disque persistant.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POINTAGE_EN_LIGNE=1 \
    POINTAGE_DATA_DIR=/data \
    POINTAGE_TZ=Africa/Casablanca

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Fichiers statiques préparés à la construction (servis par WhiteNoise).
RUN POINTAGE_DATA_DIR=/tmp/build POINTAGE_SECRET_KEY=construction python manage.py collectstatic --noinput \
    && rm -rf /tmp/build \
    && chmod +x deploiement/demarrer-en-ligne.sh

EXPOSE 8000
CMD ["deploiement/demarrer-en-ligne.sh"]
