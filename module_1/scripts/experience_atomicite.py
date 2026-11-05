"""Expérience du chapitre 2.4 : un plantage entre la commande et le paiement.

Usage : python scripts/experience_atomicite.py [--essais 200]
Tout se passe dans un schéma jetable (essai_concurrence), supprimé à la fin.
"""
import argparse
import sys

from senmarket_bases.commande import PlantageSimule, passer_commande_naive
from senmarket_bases.connexions import ErreurConnexion, connexion_postgres
from senmarket_bases.experience_concurrence import (
    SCHEMA,
    _etat,
    connexion_acheteur,
    executer_plantage,
    preparer_schema,
    remettre_a_zero,
    tableau_plantage_markdown,
)
from senmarket_bases.preuves_contraintes import supprimer_schema


def main() -> int:
    parser = argparse.ArgumentParser(description="Expérience d'atomicité.")
    parser.add_argument("--essais", type=int, default=200)
    args = parser.parse_args()
    try:
        principale = connexion_postgres()
    except ErreurConnexion as erreur:
        print(f"ERREUR : {erreur}", file=sys.stderr)
        return 1
    principale.autocommit = True
    acheteur = None
    try:
        produit_id, nom, clients = preparer_schema(principale)
        acheteur = connexion_acheteur()

        # Un seul plantage, observé en détail
        remettre_a_zero(principale, produit_id)
        try:
            passer_commande_naive(acheteur, "demo", clients[0], produit_id, planter_avant_paiement=True)
        except PlantageSimule as erreur:
            print(f"Plantage : {erreur}")
        print("État après le plantage :", _etat(principale, produit_id), "\n")

        # La même chose, répétée
        resultats = [executer_plantage(
            "Naïve (autocommit, sans transaction)", passer_commande_naive, args.essais,
            produit_id, clients, acheteur, principale, {"planter_avant_paiement": True})]
        print("--- À coller dans docs/MESURES.md ---")
        print(f"Chapitre 2.4 : plantage entre la commande et le paiement ({nom}, {produit_id})\n")
        print(tableau_plantage_markdown(resultats))
    finally:
        if acheteur:
            acheteur.close()
        supprimer_schema(principale, SCHEMA)
        principale.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
