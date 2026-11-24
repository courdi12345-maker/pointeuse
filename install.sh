#!/bin/bash
# Installation de Pointage Max (Raspberry Pi OS, Debian ou Ubuntu).
#   bash install.sh                 -> application web seule (pointage QR, Vision RH, bilan…)
#   bash install.sh --https         -> + HTTPS sur le réseau local (caméra des téléphones)
#   bash install.sh --eid           -> + borne avec lecteur de carte eID, écran LCD et LED (Raspberry Pi)
#   Les options se combinent : bash install.sh --https --eid
set -e
cd "$(dirname "$0")"
DOSSIER="$(pwd)"
UTILISATEUR="$(whoami)"
EID=0; HTTPS=0
for option in "$@"; do
  case "$option" in
    --eid) EID=1 ;;
    --https) HTTPS=1 ;;
    *) echo "Option inconnue : $option"; exit 1 ;;
  esac
done

sudo apt-get update
sudo apt-get install -y python3-venv python3-dev build-essential git libjpeg-dev zlib1g-dev

if [ "$EID" = 1 ]; then
  sudo apt-get install -y swig libpcsclite-dev pcscd libacr38u python3-rpi.gpio
  [ -d pythonbeid ] || git clone https://github.com/Lapin-Blanc/pythonbeid.git
fi

python3 -m venv --system-site-packages venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt
if [ "$EID" = 1 ]; then venv/bin/pip install pyscard; fi

venv/bin/python manage.py makemigrations pointages
venv/bin/python manage.py migrate
venv/bin/python manage.py collectstatic --noinput
venv/bin/python manage.py jours_feries_maroc
echo "Création du compte administrateur :"
venv/bin/python manage.py createsuperuser

IP="$(hostname -I | awk '{print $1}')"
NOM="$(hostname)"
installer_unite() {
  sed -e "s|@DOSSIER@|$DOSSIER|g" -e "s|@UTILISATEUR@|$UTILISATEUR|g" -e "s|@HOSTS@|localhost,127.0.0.1,$IP,$NOM.local|g" \
    "deploiement/$1" | sudo tee "/etc/systemd/system/$1" > /dev/null
}
installer_unite pointage-web.service
if [ "$HTTPS" = 1 ]; then
  # Gunicorn n'écoute plus qu'en local : Caddy reçoit les connexions et les chiffre.
  sudo sed -i -e "s|--bind 0.0.0.0:8000|--bind 127.0.0.1:8000|" \
    -e "s|^Environment=POINTAGE_TZ|Environment=POINTAGE_HTTPS=1\nEnvironment=POINTAGE_TZ|" /etc/systemd/system/pointage-web.service
fi
installer_unite pointage-sauvegarde.service
installer_unite pointage-sauvegarde.timer
[ "$EID" = 1 ] && installer_unite pointage-borne.service
sudo systemctl daemon-reload
sudo systemctl enable --now pointage-web pointage-sauvegarde.timer
[ "$EID" = 1 ] && sudo systemctl enable --now pointage-borne

if [ "$HTTPS" = 1 ]; then
  sudo apt-get install -y caddy
  sed -e "s|@IP@|$IP|g" -e "s|@NOM@|$NOM|g" deploiement/Caddyfile | sudo tee /etc/caddy/Caddyfile > /dev/null
  sudo systemctl enable caddy
  sudo systemctl restart caddy
  # Certificat racine à installer sur les téléphones (il est public, sans secret)
  for i in $(seq 1 20); do
    CA=/var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt
    sudo test -f "$CA" && break
    sleep 1
  done
  sudo cp "$CA" "$DOSSIER/certificat-pointage-max.crt" && sudo chown "$UTILISATEUR" "$DOSSIER/certificat-pointage-max.crt"
  ADRESSE="https://$IP/"
else
  ADRESSE="http://$IP:8000/"
fi

# Ancien service init.d de la version précédente
if [ -f /etc/init.d/pointage ]; then
  sudo /etc/init.d/pointage stop || true
  sudo update-rc.d -f pointage remove || true
  sudo rm -f /etc/init.d/pointage
fi

echo
echo "Pointage Max est prêt : $ADRESSE"
echo "Sauvegarde automatique chaque nuit à 2 h 30 dans $DOSSIER/sauvegardes"
[ "$HTTPS" = 1 ] && echo "Téléphones : installez le certificat depuis ${ADRESSE}certificat.crt (voir README)."
exit 0
