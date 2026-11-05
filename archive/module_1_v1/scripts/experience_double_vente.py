"""Expérience du chapitre 2.4 : deux acheteurs, un seul article, répété N fois.

Usage : python scripts/experience_double_vente.py [--essais 200]
Tout se passe dans un schéma jetable (essai_concurrence), supprimé à la fin.
"""
import argparse
import sys

from senmarket_bases.commande import passer_commande_naive
from senmarket_bases.connexions import ErreurConnexion, connexion_postgres
from senmarket_bases.experience_concurrence import (
    SCHEMA,
    connexion_acheteur,
    executer_variante,
    preparer_schema,
    tableau_markdown,
)
from senmarket_bases.preuves_contraintes import supprimer_schema


def main() -> int:
    parser = argparse.ArgumentParser(description="Expérience de double vente.")
    parser.add_argument("--essais", type=int, default=200, help="nombre d'essais par variante (200 minimum)")
    args = parser.parse_args()

    try:
        principale = connexion_postgres()
    except ErreurConnexion as erreur:
        print(f"ERREUR : {erreur}", file=sys.stderr)
        return 1
    principale.autocommit = True
    connexions = []
    try:
        produit_id, nom, clients = preparer_schema(principale)
        print(f"Produit disputé : {produit_id} ({nom}), stock de départ 1, deux acheteurs : {clients}\n")
        connexions = [connexion_acheteur(), connexion_acheteur()]

        variantes = [
            ("Naïve, sans pause", passer_commande_naive, {"pause": 0.0}),
            ("Naïve, pause de 10 ms entre lecture et écriture", passer_commande_naive, {"pause": 0.01}),
        ]
        resultats = []
        for nom_variante, fonction, options in variantes:
            r = executer_variante(nom_variante, fonction, args.essais, produit_id, clients,
                                  connexions, principale, options)
            resultats.append(r)
            print(f"{nom_variante} : {r['doubles_ventes']} double(s) vente(s) sur {r['essais']} essais"
                  f" | stock final observé lors d'une double vente : {r['stock_apres_double']}")
        print("\n--- À coller dans docs/MESURES.md ---")
        print(f"Chapitre 2.4 : double vente sur {nom} ({produit_id}), stock 1, deux acheteurs en parallèle\n")
        print(tableau_markdown(resultats))
    finally:
        for c in connexions:
            c.close()
        supprimer_schema(principale, SCHEMA)
        principale.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
