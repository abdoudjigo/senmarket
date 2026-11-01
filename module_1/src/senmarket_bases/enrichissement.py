"""Enrichissement des données du module 0 pour le module 1.

Produit, dans bases_enriched/date=AAAA-MM-JJ/, les données qui manquent à SenMarket
pour fonctionner comme un vrai magasin : stock, catalogue, commentaires, références
de transaction.

Usage : python -m senmarket_bases.enrichissement --run-date AAAA-MM-JJ
Règle d'or : relancé avec la même date, il produit des fichiers identiques.
"""
import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from senmarket_bases.catalogue_donnees import ATTRIBUTS_PAR_PRODUIT

# Racine de module_1 : enrichissement.py -> senmarket_bases -> src -> module_1
RACINE = Path(__file__).resolve().parents[2]
DOSSIER_PROCESSED = RACINE / "data" / "processed"   # lecture seule (données du module 0)
DOSSIER_SORTIE = RACINE / "bases_enriched"          # nos fichiers, séparés du module 0

# Graine de base : fixe, donc deux exécutions donnent les mêmes données
GRAINE = 42

# Un numéro par fichier : chaque fichier a son propre flux aléatoire, indépendant des autres
FLUX_STOCK = 1
FLUX_REFERENCES = 2
FLUX_COMMENTAIRES = 3

NB_RUPTURES = 5   # produits à stock 0
NB_FLASH = 3      # produits à stock 1 à 5 (épreuves de double vente du chapitre 2)

# Libellés EXACTS de methode_paiement dans les Parquet du module 0
PREFIXES = {"Wave": "WAV", "Orange Money": "OM", "Carte bancaire": "CB"}
METHODE_SANS_REFERENCE = "Espèces"   # pas d'identifiant externe pour du liquide

# Vocabulaire des commentaires : un début et une fin par note, cohérents avec la note.
# Les phrases négatives ne contiennent aucun mot positif (même nié), et inversement.
DEBUTS = {
    1: ["Très mauvaise expérience.", "Je suis très déçu.", "Vraiment décevant.",
        "Une vraie catastrophe.", "À éviter."],
    2: ["Pas terrible.", "Assez décevant.", "Je m'attendais à mieux.",
        "Bof, ça ne m'a pas convaincu.", "Plutôt moyen."],
    3: ["Correct.", "Dans la moyenne.", "Ni bon ni mauvais.", "Produit acceptable.",
        "Ça fait l'affaire."],
    4: ["Bon produit.", "Je suis content de mon achat.", "Plutôt satisfait.",
        "Bonne surprise.", "Achat réussi."],
    5: ["Excellent produit !", "Parfait, rien à redire.", "Très satisfait de mon achat.",
        "Je recommande vivement.", "Super achat !"],
}
FINS = {
    1: ["Le produit ne correspond pas à la description.",
        "La livraison a pris beaucoup trop de temps.", "Le produit est arrivé abîmé.",
        "Le service client n'a pas répondu.", "Je ne rachèterai pas."],
    2: ["La qualité est inférieure au prix demandé.", "Livraison en retard.",
        "L'emballage était abîmé.", "Quelques défauts dès la réception.",
        "Rapport qualité-prix limité."],
    3: ["Rien d'exceptionnel pour le prix.", "La livraison était dans les délais.",
        "Conforme à la description, sans plus.", "Je verrai si je rachète.",
        "Qualité honnête."],
    4: ["Livraison rapide.", "Bon rapport qualité-prix.", "Conforme à la description.",
        "Bien emballé.", "Je rachèterai sûrement."],
    5: ["Livraison très rapide.", "Qualité au rendez-vous.", "Emballage soigné.",
        "Vendeur sérieux.", "Je rachèterai sans hésiter."],
}

journal = logging.getLogger("enrichissement")


class ErreurEnrichissement(Exception):
    """Erreur courte et lisible : partition absente, date invalide, données inattendues."""


def _generateur(run_date: str, flux: int) -> np.random.Generator:
    """Générateur aléatoire reproductible : même date et même flux, mêmes tirages.

    On n'utilise jamais datetime.now() ni hash() : ils changent d'une exécution à l'autre.
    """
    return np.random.default_rng([GRAINE, int(run_date.replace("-", "")), flux])


def lire_table(nom: str, cle: str, run_date: str, dossier_processed: Path) -> pd.DataFrame:
    """Lit une table de la partition, triée par clé primaire (ordre stable)."""
    dossier = dossier_processed / f"date={run_date}"
    if not dossier.exists():
        dispo = ", ".join(sorted(p.name for p in dossier_processed.glob("date=*"))) or "aucune"
        raise ErreurEnrichissement(
            f"Partition introuvable : date={run_date}. Partitions disponibles : {dispo}"
        )
    fichier = dossier / f"{nom}.parquet"
    if not fichier.exists():
        raise ErreurEnrichissement(f"Fichier manquant : {fichier}")
    return pd.read_parquet(fichier).sort_values(cle).reset_index(drop=True)


def generer_stock(produits: pd.DataFrame, run_date: str) -> pd.DataFrame:
    """Un stock par produit : majorité entre 20 et 400, quelques ruptures, trois produits flash."""
    rng = _generateur(run_date, FLUX_STOCK)
    ids = produits["produit_id"].tolist()

    # Produits flash : le téléphone (histoire de Moussa) + des produits d'Électronique
    electro = produits.loc[produits["categorie"] == "Électronique", "produit_id"].tolist()
    if len(electro) < NB_FLASH:
        raise ErreurEnrichissement(
            f"Il faut au moins {NB_FLASH} produits d'Électronique pour les produits flash, "
            f"il y en a {len(electro)}."
        )
    telephone = produits.loc[produits["nom_produit"] == "Téléphone", "produit_id"].tolist()[:1]
    autres = [p for p in electro if p not in telephone]
    tires = rng.choice(autres, size=NB_FLASH - len(telephone), replace=False)
    flash = telephone + [str(p) for p in tires]

    # Ruptures : tirées parmi les produits qui ne sont pas flash
    candidats = [p for p in ids if p not in flash]
    ruptures = {str(p) for p in rng.choice(candidats, size=NB_RUPTURES, replace=False)}

    # Stock courant pour tous, puis on écrase les ruptures et les produits flash
    stock = rng.integers(20, 401, size=len(ids))
    stock_flash = rng.integers(1, 6, size=len(flash))   # 1 à 5 inclus

    resultat = pd.DataFrame({"produit_id": ids, "stock": stock})
    resultat.loc[resultat["produit_id"].isin(ruptures), "stock"] = 0
    for produit_id, valeur in zip(flash, stock_flash):
        resultat.loc[resultat["produit_id"] == produit_id, "stock"] = int(valeur)
    return resultat


def generer_references(paiements: pd.DataFrame, run_date: str) -> pd.DataFrame:
    """Une référence de transaction par paiement électronique, vide pour les espèces."""
    rng = _generateur(run_date, FLUX_REFERENCES)
    # Tri explicite : le résultat ne dépend pas de l'ordre des lignes en entrée
    paiements = paiements.sort_values("paiement_id").reset_index(drop=True)

    # Un libellé inconnu (faute de frappe, nouvelle méthode) doit échouer, pas passer
    connues = set(PREFIXES) | {METHODE_SANS_REFERENCE}
    inconnues = set(paiements["methode_paiement"].unique()) - connues
    if inconnues:
        raise ErreurEnrichissement(
            "Méthode(s) de paiement inconnue(s) : "
            f"{sorted(map(str, inconnues))}. Attendues : {sorted(connues)}."
        )

    electroniques = paiements["methode_paiement"].isin(PREFIXES).to_numpy()
    # Nombres à 9 chiffres tirés SANS remise : un doublon est impossible, pas seulement rare
    numeros = rng.choice(900_000_000, size=int(electroniques.sum()), replace=False) + 100_000_000
    prefixes = paiements.loc[electroniques, "methode_paiement"].map(PREFIXES)

    references = np.full(len(paiements), None, dtype=object)   # None s'écrit vide dans le CSV
    references[electroniques] = [f"{p}-{int(n)}" for p, n in zip(prefixes, numeros)]
    return pd.DataFrame(
        {"paiement_id": paiements["paiement_id"], "reference_transaction": references}
    )


def generer_commentaires(avis: pd.DataFrame, run_date: str) -> pd.DataFrame:
    """Un commentaire par avis, tiré dans le vocabulaire de SA note (début + fin)."""
    rng = _generateur(run_date, FLUX_COMMENTAIRES)
    # Tri explicite : le résultat ne dépend pas de l'ordre des lignes en entrée
    avis = avis.sort_values("avis_id").reset_index(drop=True)

    # Une note hors de 1 à 5 n'a pas de vocabulaire : on s'arrête en la nommant
    invalide = ~avis["note"].isin(list(DEBUTS))
    if invalide.any():
        raise ErreurEnrichissement(
            f"Note(s) hors de 1 à 5 : {sorted(map(str, avis.loc[invalide, 'note'].unique()))}."
        )

    commentaires = np.empty(len(avis), dtype=object)
    for note in sorted(DEBUTS):
        masque = (avis["note"] == note).to_numpy()
        n = int(masque.sum())
        debuts = rng.integers(0, len(DEBUTS[note]), size=n)
        fins = rng.integers(0, len(FINS[note]), size=n)
        commentaires[masque] = [f"{DEBUTS[note][d]} {FINS[note][f]}" for d, f in zip(debuts, fins)]
    return pd.DataFrame({"avis_id": avis["avis_id"], "commentaire": commentaires})


def generer_catalogue(produits: pd.DataFrame) -> list[dict]:
    """Un document par produit : identité + attributs variables selon le produit.

    Pas de prix ni de stock ici : ces valeurs changent et vivent dans PostgreSQL.
    """
    # Tri explicite : le résultat ne dépend pas de l'ordre des lignes en entrée
    produits = produits.sort_values("produit_id").reset_index(drop=True)

    # Un produit sans fiche d'attributs doit échouer, pas être ignoré en silence
    inconnus = sorted(set(produits["nom_produit"]) - set(ATTRIBUTS_PAR_PRODUIT))
    if inconnus:
        raise ErreurEnrichissement(
            f"Produit(s) sans attributs dans catalogue_donnees.py : {inconnus}."
        )
    return [
        {
            "produit_id": ligne.produit_id,
            "nom": ligne.nom_produit,
            "categorie": ligne.categorie,
            "attributs": ATTRIBUTS_PAR_PRODUIT[ligne.nom_produit],
        }
        for ligne in produits.itertuples()
    ]


def lancer(
    run_date: str,
    dossier_processed: Path = DOSSIER_PROCESSED,
    dossier_sortie: Path = DOSSIER_SORTIE,
) -> Path:
    """Calcule tous les fichiers en mémoire, puis les écrit. Renvoie le dossier de sortie."""
    try:
        date.fromisoformat(run_date)
    except ValueError:
        raise ErreurEnrichissement(
            f"Date invalide : '{run_date}'. Format attendu : AAAA-MM-JJ."
        ) from None

    produits = lire_table("produits", "produit_id", run_date, dossier_processed)
    paiements = lire_table("paiements", "paiement_id", run_date, dossier_processed)
    avis = lire_table("avis", "avis_id", run_date, dossier_processed)

    # 1) Tout calculer en mémoire : une erreur ici ne laisse aucun fichier à moitié écrit
    fichiers = {
        "stock.csv": generer_stock(produits, run_date),
        "paiements_references.csv": generer_references(paiements, run_date),
        "avis_commentaires.csv": generer_commentaires(avis, run_date),
        "catalogue.jsonl": generer_catalogue(produits),
    }

    # 2) Seulement ensuite, écrire
    sortie = dossier_sortie / f"date={run_date}"
    sortie.mkdir(parents=True, exist_ok=True)
    for nom, contenu in fichiers.items():
        if nom.endswith(".jsonl"):
            # Une ligne = un document. Accents écrits tels quels, clés triées : même sha256
            lignes = [json.dumps(doc, ensure_ascii=False, sort_keys=True) for doc in contenu]
            with open(sortie / nom, "w", encoding="utf-8", newline="\n") as f:
                f.write("\n".join(lignes) + "\n")
        else:
            # lineterminator fixe : le même contenu donne le même sha256 sur toute machine
            contenu.to_csv(sortie / nom, index=False, lineterminator="\n")
        journal.info("%s écrit : %d lignes", nom, len(contenu))
    return sortie


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enrichit une partition du module 0.")
    parser.add_argument("--run-date", required=True, help="date de la partition, AAAA-MM-JJ")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    try:
        sortie = lancer(args.run_date)
    except ErreurEnrichissement as erreur:
        print(f"ERREUR : {erreur}", file=sys.stderr)
        return 1
    journal.info("Terminé : %s", sortie)
    return 0


if __name__ == "__main__":
    sys.exit(main())
