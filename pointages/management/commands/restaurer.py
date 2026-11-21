from django.core.management.base import BaseCommand, CommandError

from pointages import sauvegardes


class Command(BaseCommand):
    help = "Restaure une sauvegarde .zip (l'état actuel est d'abord sauvegardé)."

    def add_arguments(self, parser):
        parser.add_argument("fichier")
        parser.add_argument("--oui", action="store_true", help="ne pas demander de confirmation")

    def handle(self, fichier, oui, **options):
        try:
            infos = sauvegardes.verifier(fichier)
        except (sauvegardes.SauvegardeInvalide, OSError) as e:
            raise CommandError("Sauvegarde refusée : %s" % e)
        self.stdout.write("Sauvegarde valide : %(employes)s employés, %(pointages)s pointages, %(fichiers)s fichiers." % infos)
        if not oui and input("Remplacer toutes les données actuelles ? Tapez OUI : ").strip() != "OUI":
            raise CommandError("Restauration annulée.")
        _, securite = sauvegardes.restaurer(fichier)
        self.stdout.write(self.style.SUCCESS("Restauration terminée. L'état précédent est conservé dans %s" % securite))
