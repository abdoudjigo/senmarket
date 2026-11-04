"""Expérience du chapitre 2.4 : comparer les trois remèdes à la double vente.

Usage : python scripts/experience_remedes.py [--essais 200]
Tout se passe dans un schéma jetable (essai_concurrence), supprimé à la fin.
"""
import argparse
import sys

from senmarket_bases.commande import (
    passer_commande_atomique,
    passer_commande_naive,
    passer_commande_serializable,
    passer_commande_verrou,
)
from senmarket_bases.connexions import ErreurConnexion, connexion_postgres
from senmarket_bases.experience_concurrence import (
    SCHEMA,
    connexion_acheteur,
    executer_plantage,
    executer_variante,
    mesurer_debit,
    preparer_schema,
    tableau_debit_markdown,
    tableau_markdown,
    tableau_plantage_markdown,
)
from senmarket_bases.preuves_contraintes import supprimer_schema

REMEDES = [
    ("Atomique (UPDATE conditionnel)", passer_commande_atomique),
    ("Verrou (SELECT FOR UPDATE)", passer_commande_verrou),
    ("SERIALIZABLE + nouvelle tentative", passer_commande_serializable),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare les remèdes à la double vente.")
    parser.add_argument("--essais", type=int, default=200)
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
        connexions = [connexion_acheteur(), connexion_acheteur()]
        print(f"Produit disputé : {produit_id} ({nom}), stock de départ 1\n")

        # 1) Double vente : deux acheteurs, un article, avec et sans pause
        doubles = []
        for nom_remede, fonction in REMEDES:
            for pause in (0.0, 0.01):
                libelle = f"{nom_remede}, " + ("sans pause" if not pause else "pause de 10 ms")
                doubles.append(executer_variante(libelle, fonction, args.essais, produit_id,
                                                 clients, connexions, principale, {"pause": pause}))
        # 2) Atomicité : plantage entre la commande et le paiement
        plantages = [executer_plantage(nom_remede, fonction, args.essais, produit_id, clients,
                                       connexions[0], principale, {"planter_avant_paiement": True})
                     for nom_remede, fonction in REMEDES]
        # 3) Débit : 8 acheteurs, 100 commandes chacun, sur le même produit
        debits = [mesurer_debit("Naïve (pour comparaison)", passer_commande_naive, produit_id,
                                clients, principale)]
        debits += [mesurer_debit(nom_remede, fonction, produit_id, clients, principale)
                   for nom_remede, fonction in REMEDES]

        print("--- À coller dans docs/MESURES.md ---\n")
        print(f"Chapitre 2.4 : les trois remèdes, sur {nom} ({produit_id})\n")
        print("### Double vente (deux acheteurs, stock 1)\n")
        print(tableau_markdown(doubles))
        print("\n### Plantage entre la commande et le paiement\n")
        print(tableau_plantage_markdown(plantages))
        print("\n### Débit (8 acheteurs x 100 commandes sur le même produit, stock 10 000)\n")
        print(tableau_debit_markdown(debits))
    finally:
        for c in connexions:
            c.close()
        supprimer_schema(principale, SCHEMA)
        principale.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
