"""Connexion protégée contre les essais de mots de passe à répétition.

Après CONNEXION_ESSAIS_MAX échecs depuis la même adresse, cette adresse est bloquée
CONNEXION_BLOCAGE_MINUTES minutes. Une connexion réussie remet le compteur à zéro.
"""

import logging

from django import forms
from django.conf import settings
from django.contrib.auth import views as auth_views
from django.contrib.auth.forms import AuthenticationForm
from django.core.cache import cache

log = logging.getLogger("pointages")


def adresse_ip(request):
    """Adresse du visiteur. Derrière l'hébergeur (version en ligne), c'est le premier élément de
    X-Forwarded-For ; en local on ne s'y fie pas, car n'importe qui peut écrire cet en-tête."""
    if getattr(settings, "EN_LIGNE", False):
        transmis = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if transmis:
            return transmis.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "inconnue")


def _cle(ip):
    return "connexion-echecs:%s" % ip


def est_bloquee(ip):
    return cache.get(_cle(ip), 0) >= settings.CONNEXION_ESSAIS_MAX


def noter_echec(ip):
    cle = _cle(ip)
    n = cache.get(cle, 0) + 1
    cache.set(cle, n, settings.CONNEXION_BLOCAGE_MINUTES * 60)
    return n


class FormulaireConnexion(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Identifiant ou mot de passe incorrect.",
        "inactive": "Ce compte est désactivé.",
    }

    def clean(self):
        ip = adresse_ip(self.request)
        if est_bloquee(ip):
            raise forms.ValidationError(
                "Trop d'essais incorrects. Réessayez dans %d minutes." % settings.CONNEXION_BLOCAGE_MINUTES,
                code="bloque")
        try:
            return super().clean()
        except forms.ValidationError:
            n = noter_echec(ip)
            log.warning("Échec de connexion %d/%d depuis %s (identifiant « %s »)",
                        n, settings.CONNEXION_ESSAIS_MAX, ip, (self.data.get("username") or "")[:50])
            raise


class VueConnexion(auth_views.LoginView):
    template_name = "pointages/connexion.html"
    authentication_form = FormulaireConnexion

    def form_valid(self, form):
        cache.delete(_cle(adresse_ip(self.request)))
        return super().form_valid(form)
