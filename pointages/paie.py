"""Calcul indicatif d'une fiche de paie mensuelle (Maroc).

Le salaire brut vient du bilan mensuel (heures, jours, congés payés). Les retenues
(CNSS, AMO, IR) suivent les paramètres POINTAGE_MAX["PAIE"] : montants indicatifs,
à faire valider par un comptable.
"""
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings

from . import stats


def _d(x):
    return Decimal(str(x))


def _arrondi(x):
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def personnes_a_charge(personne):
    p = settings.POINTAGE_MAX["PAIE"]
    n = (1 if personne.situation_familiale == "marie" else 0) + (personne.enfants or 0)
    return min(n, p["IR_PERSONNES_MAX"])


def ir_mensuel(net_imposable, personnes):
    p = settings.POINTAGE_MAX["PAIE"]
    annuel = net_imposable * 12
    ir = Decimal(0)
    for plafond, taux, deduction in p["IR_BAREME_ANNUEL"]:
        if plafond is None or annuel <= plafond:
            ir = annuel * _d(taux) - _d(deduction)
            break
    ir -= _d(p["IR_DEDUCTION_PAR_PERSONNE_ANNUELLE"]) * personnes
    return max(ir / 12, Decimal(0))


def retenues(brut, personne):
    """Renvoie le détail des retenues et le net à payer pour un salaire brut mensuel."""
    p = settings.POINTAGE_MAX["PAIE"]
    if not p["ACTIVE"]:
        return {"lignes": [], "total": Decimal(0), "net": _arrondi(brut), "imposable": None}
    cnss = min(brut, _d(p["CNSS_PLAFOND_MENSUEL"])) * _d(p["CNSS_TAUX"])
    amo = brut * _d(p["AMO_TAUX"])
    if brut * 12 <= _d(p["FRAIS_PRO_SEUIL_ANNUEL"]):
        frais = brut * _d(p["FRAIS_PRO_TAUX_BAS"])
    else:
        frais = min(brut * _d(p["FRAIS_PRO_TAUX_HAUT"]), _d(p["FRAIS_PRO_PLAFOND_ANNUEL"]) / 12)
    imposable = max(brut - cnss - amo - frais, Decimal(0))
    pac = personnes_a_charge(personne)
    ir = ir_mensuel(imposable, pac)
    lignes = [
        {"libelle": "CNSS (prestations sociales)", "base": min(brut, _d(p["CNSS_PLAFOND_MENSUEL"])),
         "taux": _d(p["CNSS_TAUX"]) * 100, "montant": _arrondi(cnss)},
        {"libelle": "AMO (assurance maladie)", "base": brut, "taux": _d(p["AMO_TAUX"]) * 100, "montant": _arrondi(amo)},
        {"libelle": "IR (impôt sur le revenu) — %d personne(s) à charge" % pac, "base": _arrondi(imposable),
         "taux": None, "montant": _arrondi(ir)},
    ]
    total = sum(l["montant"] for l in lignes)
    return {"lignes": lignes, "total": total, "net": _arrondi(brut) - total,
            "imposable": _arrondi(imposable), "frais_pro": _arrondi(frais)}


def fiche(personne, annee, mois):
    ligne = stats.bilan_mensuel(annee, mois, personne=personne)
    l = ligne["lignes"][0]
    brut = l["reel"]
    return {"personne": personne, "annee": annee, "mois": mois, "bilan": l,
            "debut": ligne["debut"], "fin": ligne["fin"], "jours_ouvres": ligne["jours_ouvres"],
            "brut": brut, "retenues": retenues(brut, personne)}
