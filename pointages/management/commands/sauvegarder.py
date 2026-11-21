from django.core.management.base import BaseCommand

from pointages import sauvegardes


class Command(BaseCommand):
    help = "Crée une sauvegarde (base + photos et documents) dans le dossier des sauvegardes."

    def add_arguments(self, parser):
        parser.add_argument("--motif", default="auto", help="mot ajouté au nom du fichier (lettres et tirets)")

    def handle(self, motif, **options):
        chemin = sauvegardes.creer(motif)
        self.stdout.write(self.style.SUCCESS("Sauvegarde créée : %s" % chemin))
