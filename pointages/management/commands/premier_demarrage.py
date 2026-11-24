import os

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = ("Crée le premier compte administrateur s'il n'existe encore aucun utilisateur. "
            "En local : admin / admin123. En ligne : identifiant POINTAGE_ADMIN_USER (admin par défaut) "
            "et mot de passe POINTAGE_ADMIN_PASSWORD, obligatoire.")

    def handle(self, **options):
        if User.objects.exists():
            return
        identifiant = os.environ.get("POINTAGE_ADMIN_USER", "").strip() or "admin"
        mot_de_passe = os.environ.get("POINTAGE_ADMIN_PASSWORD", "")

        if not getattr(settings, "EN_LIGNE", False) and not mot_de_passe:
            User.objects.create_superuser(identifiant, "", "admin123")
            self.stdout.write(self.style.WARNING(
                "Compte créé : identifiant « %s », mot de passe « admin123 ». "
                "Changez-le dès la première connexion (clic sur votre nom en haut à droite)." % identifiant))
            return

        if not mot_de_passe:
            raise CommandError("Version en ligne : choisissez le mot de passe administrateur dans la "
                               "variable POINTAGE_ADMIN_PASSWORD (aucun mot de passe par défaut sur Internet).")
        utilisateur = User(username=identifiant)
        try:
            validate_password(mot_de_passe, utilisateur)
        except ValidationError as e:
            raise CommandError("Mot de passe POINTAGE_ADMIN_PASSWORD refusé : " + " ".join(e.messages))
        User.objects.create_superuser(identifiant, "", mot_de_passe)
        self.stdout.write(self.style.SUCCESS("Compte administrateur « %s » créé." % identifiant))
