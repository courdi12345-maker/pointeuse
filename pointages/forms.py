from datetime import datetime, timedelta

from django import forms
from django.utils import timezone

from .models import Conge, Entreprise, Personne, Service, Ville, jours_ouvres


class DateInput(forms.DateInput):
    input_type = "date"


class TimeInput(forms.TimeInput):
    input_type = "time"


class PersonneForm(forms.ModelForm):
    class Meta:
        model = Personne
        fields = [
            "photo", "nom", "prenoms", "sexe", "date_naissance", "lieu_naissance", "nationalite",
            "cin", "cnss", "telephone", "email", "situation_familiale", "enfants",
            "adresse", "code_postal", "localite",
            "poste", "qualification", "ville", "service", "contrat", "date_entree", "date_sortie",
            "mode_paie", "taux", "paiement_banque", "banque", "rib", "document",
        ]
        widgets = {"date_naissance": DateInput(), "date_entree": DateInput(), "date_sortie": DateInput()}

    GROUPES = [
        ("Identité", ["photo", "nom", "prenoms", "sexe", "date_naissance", "lieu_naissance", "nationalite", "cin", "cnss"]),
        ("Contact et famille", ["telephone", "email", "situation_familiale", "enfants", "adresse", "code_postal", "localite"]),
        ("Poste", ["poste", "qualification", "ville", "service", "contrat", "date_entree", "date_sortie"]),
        ("Paie et banque", ["mode_paie", "taux", "paiement_banque", "banque", "rib"]),
        ("Pièce d'identité scannée", ["document"]),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["photo"].widget.attrs["accept"] = "image/*"
        self.fields["document"].widget.attrs["accept"] = "image/*,application/pdf"

    def groupes(self):
        for titre, noms in self.GROUPES:
            champs = [self[n] for n in noms if n in self.fields]
            if champs:
                yield titre, champs


class LieuForm(forms.Form):
    ville = forms.ModelChoiceField(Ville.objects.all(), required=False, empty_label="— Toutes —")
    service = forms.ModelChoiceField(Service.objects.all(), required=False, empty_label="— Tous —",
                                     label="Service / chantier")


class PointageManuelForm(forms.Form):
    """Saisie d'un pointage. Le pointeur ne choisit que les heures : la date est celle du jour."""
    personne = forms.ModelChoiceField(Personne.objects.filter(actif=True), label="Employé")
    date = forms.DateField(widget=DateInput(), required=False)
    arrivee = forms.TimeField(widget=TimeInput(), label="Arrivée")
    depart = forms.TimeField(widget=TimeInput(), label="Départ", required=False)
    ville = forms.ModelChoiceField(Ville.objects.all(), required=False)
    service = forms.ModelChoiceField(Service.objects.all(), required=False, label="Service / chantier")

    def __init__(self, *args, admin=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.admin = admin
        if not admin:
            del self.fields["date"]

    def clean(self):
        data = super().clean()
        jour = data.get("date") if self.admin else None
        jour = jour or timezone.localdate()
        if data.get("arrivee"):
            data["checkin"] = timezone.make_aware(datetime.combine(jour, data["arrivee"]))
        data["checkout"] = (timezone.make_aware(datetime.combine(jour, data["depart"]))
                            if data.get("depart") else None)
        if data.get("checkin") and data["checkout"] and data["checkout"] <= data["checkin"]:
            raise forms.ValidationError("L'heure de départ doit être après l'heure d'arrivée.")
        if data.get("checkin") and data["checkin"] > timezone.now() + timedelta(minutes=5):
            raise forms.ValidationError("On ne peut pas pointer une heure dans le futur.")
        personne = data.get("personne")
        if personne and data.get("checkin"):
            fin = data["checkout"] or data["checkin"]
            chevauche = personne.pointage_set.filter(checkin__date=jour).exclude(pk=self.initial.get("pk"))
            for p in chevauche:
                p_fin = p.checkout or timezone.now()
                if p.checkin <= fin and data["checkin"] <= p_fin:
                    raise forms.ValidationError(
                        "Ce pointage chevauche un pointage existant (%s). Contactez l'administrateur pour le corriger."
                        % timezone.localtime(p.checkin).strftime("%H:%M"))
        return data


# ---------------------------------------------------------------------------
# Congés
# ---------------------------------------------------------------------------

class CongeForm(forms.ModelForm):
    class Meta:
        model = Conge
        fields = ["personne", "type", "debut", "fin", "motif"]
        widgets = {"debut": DateInput(), "fin": DateInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["personne"].queryset = Personne.objects.filter(actif=True)
        self.avertissement = None

    def clean(self):
        from .conges import disponible

        data = super().clean()
        debut, fin, personne = data.get("debut"), data.get("fin"), data.get("personne")
        if debut and fin and fin < debut:
            raise forms.ValidationError("La date de fin doit être après la date de début.")
        if personne and debut and fin:
            autres = personne.conge_set.filter(debut__lte=fin, fin__gte=debut).exclude(pk=self.instance.pk)
            if autres.exists():
                c = autres.first()
                raise forms.ValidationError("Ce congé chevauche un autre congé de %s (du %s au %s)." % (
                    personne, c.debut.strftime("%d/%m/%Y"), c.fin.strftime("%d/%m/%Y")))
            if data.get("type") == "annuel":
                demande = jours_ouvres(debut, fin)
                dispo = disponible(personne)
                if self.instance.pk and self.instance.type == "annuel":
                    dispo += self.instance.jours_ouvres()
                if demande > dispo:
                    self.avertissement = ("Attention : %s jour(s) décompté(s) pour un solde disponible de %s jour(s). "
                                          "Le congé est enregistré, le solde devient négatif." % (demande, dispo))
        return data


# ---------------------------------------------------------------------------
# Utilisateurs
# ---------------------------------------------------------------------------

ROLE_CHOICES = (("pointeur", "Pointeur"), ("admin", "Administrateur"))


class UtilisateurForm(forms.Form):
    username = forms.RegexField(r"^[\w.@+-]+$", max_length=150, label="Identifiant",
                                error_messages={"invalid": "Lettres, chiffres et . @ + - _ uniquement."})
    first_name = forms.CharField(max_length=150, required=False, label="Prénom")
    last_name = forms.CharField(max_length=150, required=False, label="Nom")
    role = forms.ChoiceField(choices=ROLE_CHOICES, label="Rôle")
    actif = forms.BooleanField(required=False, initial=True, label="Compte actif")
    password1 = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
                                required=False, label="Mot de passe")
    password2 = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
                                required=False, label="Confirmer le mot de passe")

    def __init__(self, *args, utilisateur=None, demandeur=None, **kwargs):
        self.utilisateur, self.demandeur = utilisateur, demandeur
        super().__init__(*args, **kwargs)
        if utilisateur:
            self.fields["password1"].help_text = "Laisser vide pour ne pas changer le mot de passe."

    def clean_username(self):
        from django.contrib.auth.models import User
        nom = self.cleaned_data["username"]
        qs = User.objects.filter(username__iexact=nom)
        if self.utilisateur:
            qs = qs.exclude(pk=self.utilisateur.pk)
        if qs.exists():
            raise forms.ValidationError("Cet identifiant est déjà utilisé.")
        return nom

    def clean(self):
        from django.contrib.auth import password_validation
        data = super().clean()
        p1, p2 = data.get("password1"), data.get("password2")
        if not self.utilisateur and not p1:
            self.add_error("password1", "Le mot de passe est obligatoire pour un nouveau compte.")
        if p1 or p2:
            if p1 != p2:
                self.add_error("password2", "Les deux mots de passe ne sont pas identiques.")
            else:
                try:
                    password_validation.validate_password(p1, self.utilisateur)
                except forms.ValidationError as e:
                    self.add_error("password1", e)
        if self.utilisateur and self.utilisateur == self.demandeur:
            if data.get("role") != "admin" or not data.get("actif"):
                raise forms.ValidationError("Vous ne pouvez pas retirer vos propres droits d'administrateur "
                                            "ni désactiver votre propre compte.")
        return data


class EntrepriseForm(forms.ModelForm):
    class Meta:
        model = Entreprise
        fields = ["raison_sociale", "adresse", "ville", "telephone", "email", "ice", "rc",
                  "identifiant_fiscal", "cnss", "logo"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["logo"].widget.attrs["accept"] = "image/*"
