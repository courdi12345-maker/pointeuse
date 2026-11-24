"""Calculs du tableau de bord (Vision RH) et du bilan mensuel."""
import calendar
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .models import Conge, Personne, Pointage, jours_ouvres

CONGES_PAYES = ("annuel", "maternite")


def cfg(cle):
    return settings.POINTAGE_MAX[cle]


def bornes_mois(annee, mois):
    return date(annee, mois, 1), date(annee, mois, calendar.monthrange(annee, mois)[1])


def mois_precedent(annee, mois):
    return (annee - 1, 12) if mois == 1 else (annee, mois - 1)


def arrondi(x, n="0.01"):
    return Decimal(x).quantize(Decimal(n), rounding=ROUND_HALF_UP)


def heures(td):
    return Decimal(td.total_seconds()) / Decimal(3600)


def format_heures(h):
    minutes = int(round(float(h) * 60))
    return "%dh%02d" % (minutes // 60, minutes % 60)


def _pointages_periode(debut, fin, personnes=None):
    qs = Pointage.objects.filter(checkin__date__range=(debut, fin)).select_related(
        "personne", "ville", "service", "personne__service")
    if personnes is not None:
        qs = qs.filter(personne__in=personnes)
    return qs


def _jours_conge(personne_ids, debut, fin, types=None):
    """{personne_id: {type: nb_jours_ouvres}} pour les congés qui touchent la période."""
    qs = Conge.objects.filter(personne_id__in=personne_ids, debut__lte=fin, fin__gte=debut)
    if types:
        qs = qs.filter(type__in=types)
    res = defaultdict(lambda: defaultdict(int))
    for c in qs:
        res[c.personne_id][c.type] += jours_ouvres(max(c.debut, debut), min(c.fin, fin))
    return res


# ---------------------------------------------------------------------------
# Bilan mensuel
# ---------------------------------------------------------------------------

def salaire(personne, h, jours_travailles, jours_conges_payes, jours_ouvres_mois):
    """Renvoie (théorique, réel) pour le mois."""
    hm = Decimal(cfg("HEURES_MENSUELLES"))
    hj = Decimal(cfg("HEURES_PAR_JOUR"))
    taux = personne.taux
    if personne.mode_paie == "M":
        theorique = taux
        h_payees = h + jours_conges_payes * hj
        reel = min(taux, taux * h_payees / hm) if hm else Decimal(0)
    elif personne.mode_paie == "J":
        theorique = taux * jours_ouvres_mois
        reel = taux * (jours_travailles + jours_conges_payes)
    else:
        theorique = taux * hm
        reel = taux * (h + jours_conges_payes * hj)
    return arrondi(theorique), arrondi(reel)


def bilan_mensuel(annee, mois, ville=None, service=None, personne=None):
    debut, fin = bornes_mois(annee, mois)
    personnes = Personne.objects.select_related("service", "ville", "contrat")
    if personne:
        personnes = personnes.filter(pk=personne.pk)
    else:
        personnes = personnes.filter(Q(actif=True) | Q(pointage__checkin__date__range=(debut, fin))).distinct()
    if ville:
        personnes = personnes.filter(ville=ville)
    if service:
        personnes = personnes.filter(service=service)
    personnes = list(personnes)

    jom = jours_ouvres(debut, fin)
    aujourd_hui = timezone.localdate()
    # Pour le mois en cours, les absences ne se comptent que sur les jours déjà passés.
    jours_ecoules = jours_ouvres(debut, min(fin, aujourd_hui)) if debut <= aujourd_hui else 0
    conges_ecoules = _jours_conge([p.pk for p in personnes], debut, min(fin, aujourd_hui)) if debut <= aujourd_hui else {}
    par_personne = defaultdict(lambda: {"td": timedelta(), "jours": set(), "ouverts": 0})
    for p in _pointages_periode(debut, fin, personnes):
        d = par_personne[p.personne_id]
        jour = timezone.localtime(p.checkin).date()
        d["jours"].add(jour)
        if p.checkout:
            d["td"] += p.checkout - p.checkin
        elif jour < aujourd_hui:
            d["ouverts"] += 1  # sortie oubliée (ceux d'aujourd'hui sont simplement présents)
    conges = _jours_conge([p.pk for p in personnes], debut, fin)

    lignes = []
    tot = {"heures": Decimal(0), "theorique": Decimal(0), "reel": Decimal(0), "jours": 0}
    for p in personnes:
        d = par_personne[p.pk]
        h = heures(d["td"])
        jc_payes = sum(v for k, v in conges[p.pk].items() if k in CONGES_PAYES)
        jc_total = sum(conges[p.pk].values())
        theo, reel = salaire(p, h, len(d["jours"]), jc_payes, jom)
        lignes.append({
            "personne": p, "jours": len(d["jours"]), "heures": h, "heures_txt": format_heures(h),
            "conges": jc_total, "ouverts": d["ouverts"],
            "absences": max(jours_ecoules - len(d["jours"])
                            - sum(conges_ecoules.get(p.pk, {}).values()), 0),
            "theorique": theo, "reel": reel,
        })
        tot["heures"] += h
        tot["theorique"] += theo
        tot["reel"] += reel
        tot["jours"] += len(d["jours"])
    tot["heures_txt"] = format_heures(tot["heures"])
    lignes.sort(key=lambda l: (l["personne"].nom, l["personne"].prenoms))
    return {"lignes": lignes, "total": tot, "jours_ouvres": jom, "debut": debut, "fin": fin}


# ---------------------------------------------------------------------------
# Tableau de bord
# ---------------------------------------------------------------------------

def _limite_retard(personne, jour):
    service = personne.service
    h = service.heure_debut if service else datetime.strptime(cfg("HEURE_DEBUT"), "%H:%M").time()
    limite = datetime.combine(jour, h) + timedelta(minutes=cfg("TOLERANCE_RETARD_MINUTES"))
    return timezone.make_aware(limite)


def premieres_arrivees(pointages):
    """{(personne_id, jour): (personne, premier checkin)}"""
    res = {}
    for p in pointages:
        cle = (p.personne_id, timezone.localtime(p.checkin).date())
        if cle not in res or p.checkin < res[cle][1]:
            res[cle] = (p.personne, p.checkin)
    return res


def employes_attendus(jour):
    """Employés en poste à cette date (entrés avant, pas encore sortis)."""
    qs = Personne.objects.select_related("service", "ville").filter(
        Q(date_entree__isnull=True) | Q(date_entree__lte=jour)).filter(
        Q(date_sortie__isnull=True, actif=True) | Q(date_sortie__gte=jour))
    return list(qs)


def type_de_jour(jour, feries=None):
    """(« ouvré » | « repos » | « férié », libellé)"""
    from .models import JourFerie
    if feries is None:
        feries = {f.date: f.nom for f in JourFerie.objects.filter(date=jour)}
    if jour in feries:
        return "ferie", feries[jour]
    if jour.weekday() in cfg("JOURS_REPOS"):
        return "repos", "Jour de repos"
    return "ouvre", ""


def _retard(pers, jour, checkin):
    limite = _limite_retard(pers, jour)
    if checkin > limite:
        return int((checkin - limite).total_seconds() // 60) + cfg("TOLERANCE_RETARD_MINUTES")
    return 0


def journee(jour):
    """Analyse détaillée d'une journée."""
    aujourd_hui = timezone.localdate()
    attendus = employes_attendus(jour)
    pointages = sorted(_pointages_periode(jour, jour), key=lambda p: p.checkin)
    pointes = {p.personne_id for p in pointages}
    ouverts = [p for p in pointages if not p.checkout]
    en_conge = list(Conge.objects.filter(debut__lte=jour, fin__gte=jour).select_related("personne"))
    ids_conge = {c.personne_id for c in en_conge}
    nature, libelle = type_de_jour(jour)
    futur = jour > aujourd_hui
    absents = [] if (futur or nature != "ouvre") else [
        p for p in attendus if p.pk not in pointes and p.pk not in ids_conge]

    premieres = premieres_arrivees(pointages)
    retards = []
    for (pid, j), (pers, checkin) in premieres.items():
        # Pas de retard un jour férié ou de repos : aucune heure d'arrivée n'est prévue.
        minutes = _retard(pers, j, checkin) if nature == "ouvre" else 0
        if minutes:
            retards.append({"personne": pers, "arrivee": checkin, "minutes": minutes})
    retards.sort(key=lambda r: -r["minutes"])
    ids_retard = {r["personne"].pk for r in retards}

    # Une ligne par employé ayant pointé : première arrivée, dernière sortie, total travaillé
    lignes = {}
    for p in pointages:
        l = lignes.setdefault(p.personne_id, {"personne": p.personne, "arrivee": p.checkin, "sortie": None,
                                              "td": timedelta(), "passages": 0, "en_cours": False,
                                              "service": p.service})
        l["passages"] += 1
        if p.checkout:
            l["td"] += p.checkout - p.checkin
            l["sortie"] = max(l["sortie"], p.checkout) if l["sortie"] else p.checkout
        else:
            l["en_cours"] = True
    for l in lignes.values():
        l["duree"] = format_heures(heures(l["td"]))
        l["retard"] = next((r["minutes"] for r in retards if r["personne"].pk == l["personne"].pk), 0)
    total = sum((l["td"] for l in lignes.values()), timedelta())
    nb_premieres = len(premieres)
    return {
        "jour": jour, "est_aujourd_hui": jour == aujourd_hui, "futur": futur,
        "nature": nature, "libelle": libelle,
        "nb_attendus": len(attendus), "nb_pointes": len(pointes),
        "presents": ouverts, "nb_presents": len({p.personne_id for p in ouverts}),
        "nb_sortis": len(pointes) - len({p.personne_id for p in ouverts}),
        "absents": absents, "en_conge": en_conge, "retards": retards,
        "heures": format_heures(heures(total)),
        "ponctualite": (int((nb_premieres - len(ids_retard)) * 100 / nb_premieres)
                        if nb_premieres and nature == "ouvre" else None),
        "lignes": sorted(lignes.values(), key=lambda l: l["arrivee"]),
    }


def calendrier(annee, mois, jour_choisi=None):
    """Semaines du mois (lundi → dimanche), avec les chiffres de chaque jour."""
    from .models import JourFerie

    debut, fin = bornes_mois(annee, mois)
    aujourd_hui = timezone.localdate()
    feries = {f.date: f.nom for f in JourFerie.objects.filter(date__range=(debut, fin))}
    par_jour = defaultdict(lambda: {"pointes": set(), "td": timedelta(), "retards": 0})
    pts = list(_pointages_periode(debut, fin))
    for p in pts:
        d = par_jour[timezone.localtime(p.checkin).date()]
        d["pointes"].add(p.personne_id)
        if p.checkout:
            d["td"] += p.checkout - p.checkin
    for (pid, j), (pers, checkin) in premieres_arrivees(pts).items():
        if type_de_jour(j, feries)[0] == "ouvre" and _retard(pers, j, checkin):
            par_jour[j]["retards"] += 1
    conges = list(Conge.objects.filter(debut__lte=fin, fin__gte=debut))
    personnes = list(Personne.objects.only("pk", "actif", "date_entree", "date_sortie"))

    def attendus(j):
        return [p.pk for p in personnes
                if (p.date_entree is None or p.date_entree <= j)
                and ((p.date_sortie is None and p.actif) or (p.date_sortie and p.date_sortie >= j))]

    max_h = max((heures(d["td"]) for d in par_jour.values()), default=0) or 1
    semaines, semaine = [], [None] * debut.weekday()
    j = debut
    while j <= fin:
        d = par_jour.get(j, {"pointes": set(), "td": timedelta(), "retards": 0})
        nature, libelle = type_de_jour(j, feries)
        en_conge = {c.personne_id for c in conges if c.debut <= j <= c.fin}
        ids = attendus(j)
        absents = (len([i for i in ids if i not in d["pointes"] and i not in en_conge])
                   if nature == "ouvre" and j <= aujourd_hui else None)
        h = heures(d["td"])
        semaine.append({
            "date": j, "jour": j.day, "nature": nature, "libelle": libelle,
            "futur": j > aujourd_hui, "aujourd_hui": j == aujourd_hui, "choisi": j == jour_choisi,
            "pointes": len(d["pointes"]), "attendus": len(ids), "heures": format_heures(h) if h else "",
            "pct": int(h * 100 / max_h), "retards": d["retards"], "absents": absents, "conges": len(en_conge),
        })
        if len(semaine) == 7:
            semaines.append(semaine)
            semaine = []
        j += timedelta(days=1)
    if semaine:
        semaines.append(semaine + [None] * (7 - len(semaine)))
    return semaines


def tableau_de_bord(annee, mois, jour=None):
    aujourd_hui = timezone.localdate()
    jour = jour or aujourd_hui
    actifs = list(Personne.objects.filter(actif=True).select_related("service", "ville"))
    sorties_oubliees = list(Pointage.objects.filter(checkout__isnull=True, checkin__date__lt=aujourd_hui)
                            .select_related("personne", "service").order_by("-checkin")[:50])
    conges_a_venir = list(Conge.objects.filter(debut__gt=aujourd_hui, debut__lte=aujourd_hui + timedelta(days=30))
                          .select_related("personne").order_by("debut"))
    j = journee(jour)

    # --- Mois choisi
    from .models import JourFerie
    debut, fin = bornes_mois(annee, mois)
    feries_mois = {f.date: f.nom for f in JourFerie.objects.filter(date__range=(debut, fin))}
    pts_mois = list(_pointages_periode(debut, fin))
    par_ville, par_service = defaultdict(Decimal), defaultdict(Decimal)
    par_personne = defaultdict(Decimal)
    for p in pts_mois:
        if not p.checkout:
            continue
        h = heures(p.checkout - p.checkin)
        par_ville[p.ville.nom if p.ville else "Sans ville"] += h
        par_service[p.service.nom if p.service else "Sans service"] += h
        par_personne[p.personne] += h

    for pers in actifs:
        par_personne.setdefault(pers, Decimal(0))

    a_l_heure = en_retard = 0
    for (pid, j_arr), (pers, checkin) in premieres_arrivees(pts_mois).items():
        if type_de_jour(j_arr, feries_mois)[0] != "ouvre":
            continue
        if checkin > _limite_retard(pers, j_arr):
            en_retard += 1
        else:
            a_l_heure += 1
    total_arrivees = a_l_heure + en_retard

    bilan = bilan_mensuel(annee, mois)
    pa, pm = mois_precedent(annee, mois)
    bilan_prec = bilan_mensuel(pa, pm)

    def variation(a, b):
        if not b:
            return None
        return arrondi((Decimal(a) - Decimal(b)) * 100 / Decimal(b), "0.1")

    classement = sorted(((pers, h) for pers, h in par_personne.items()), key=lambda x: -x[1])

    def barres(d):
        m = max(d.values(), default=0) or 1
        return [{"nom": k, "heures": format_heures(v), "pct": int(v * 100 / m)}
                for k, v in sorted(d.items(), key=lambda x: -x[1])]

    return {
        "aujourd_hui": aujourd_hui, "j": j, "calendrier": calendrier(annee, mois, jour),
        "presents": j["presents"], "absents": j["absents"],
        "sorties_oubliees": sorties_oubliees, "conges_a_venir": conges_a_venir,
        "heures_mois": bilan["total"]["heures_txt"], "heures_prec": bilan_prec["total"]["heures_txt"],
        "var_heures": variation(bilan["total"]["heures"], bilan_prec["total"]["heures"]),
        "cout_reel": bilan["total"]["reel"], "cout_theorique": bilan["total"]["theorique"],
        "cout_prec": bilan_prec["total"]["reel"],
        "var_cout": variation(bilan["total"]["reel"], bilan_prec["total"]["reel"]),
        "ponctualite": int(a_l_heure * 100 / total_arrivees) if total_arrivees else None,
        "a_l_heure": a_l_heure, "en_retard": en_retard,
        "par_ville": barres(par_ville), "par_service": barres(par_service),
        "top": [(p, format_heures(h)) for p, h in classement[:5]],
        "flop": [(p, format_heures(h)) for p, h in classement[::-1][:5]],
    }
