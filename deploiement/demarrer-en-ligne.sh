#!/bin/sh
# Démarrage de Pointage Max chez un hébergeur (Docker). Les données sont dans $POINTAGE_DATA_DIR.
set -e
cd /app
python manage.py makemigrations pointages --noinput
python manage.py migrate --noinput
python manage.py jours_feries_maroc > /dev/null
python manage.py premier_demarrage
python manage.py sauvegarder --motif demarrage || echo "Sauvegarde de démarrage impossible, on continue."

# Sauvegarde automatique une fois par jour (gardée dans le dossier des données).
(
  while true; do
    sleep 86400
    python manage.py sauvegarder --motif quotidienne || echo "Sauvegarde quotidienne échouée."
  done
) &

exec gunicorn pointeuse.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${POINTAGE_WORKERS:-2}" --threads 4 --timeout 120 \
  --forwarded-allow-ips="*" \
  --access-logfile - --error-logfile -
