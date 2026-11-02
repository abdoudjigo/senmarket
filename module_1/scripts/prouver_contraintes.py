"""Prouve que chaque contrainte du schéma refuse ce qu'elle doit refuser.

Usage : python scripts/prouver_contraintes.py
Tout se passe dans un schéma jetable (essai_preuves), supprimé à la fin : principal et
volume ne sont jamais touchés. Écrit les résultats dans docs/CONTRAINTES.md.
Code de retour 1 si une contrainte n'a pas réagi comme prévu.
"""
import sys
from pathlib import Path

from senmarket_bases.connexions import ErreurConnexion, connexion_postgres
from senmarket_bases.preuves_contraintes import (
    creer_schema,
    executer_comportements,
    executer_refus,
    preparer_donnees,
    supprimer_schema,
)

RACINE = Path(__file__).resolve().parents[1]
SCHEMA = "essai_preuves"
SORTIE = RACINE / "docs" / "CONTRAINTES.md"


def ecrire(refus: list[dict], comportements: list[tuple[str, str, bool]]) -> None:
    """Écrit le document de preuves."""
    lignes = [
        "# Preuves : les contraintes du schéma refusent ce qu'elles doivent refuser",
        "",
        "Fichier généré par `scripts/prouver_contraintes.py`, ne pas modifier à la main.",
        "Les essais ont lieu dans un schéma jetable créé avec `sql/01_schema.sql`, puis "
        "supprimé : `principal` et `volume` ne sont jamais touchés.",
        "",
        "Une règle qu'on n'a jamais vue refuser n'est pas une règle testée. Pour chaque "
        "type de contrainte, on tente donc une insertion interdite et on note la réponse "
        "exacte de PostgreSQL. Le **code SQLSTATE** est le numéro d'erreur standard : il "
        "dit de quel type de règle il s'agit, quelle que soit la langue du message.",
        "",
        "## 1. Ce que PostgreSQL refuse",
        "",
    ]
    for i, f in enumerate(refus, 1):
        verdict = "refusé comme prévu" if f["ok"] else "PROBLÈME : pas la réaction attendue"
        lignes += [
            f"### {i}. {f['categorie']} : {f['description']}",
            "",
            "```sql", f["sql"], "```",
            "",
            f"- Verdict : **{verdict}**",
            f"- Erreur attendue : `{f['attendu']}`, obtenue : `{f['obtenu']}` (SQLSTATE {f['sqlstate']})",
            f"- Contrainte en cause : `{f['contrainte']}`",
            f"- Message de PostgreSQL : {f['message']}",
            "",
        ]
    lignes += ["## 2. Ce que PostgreSQL accepte, et ce que font les ON DELETE", ""]
    for i, (description, observation, ok) in enumerate(comportements, 1):
        verdict = "conforme" if ok else "PROBLÈME"
        lignes += [f"{i}. **{description}**", f"   - Observé : {observation}",
                   f"   - Verdict : {verdict}", ""]
    SORTIE.write_text("\n".join(lignes), encoding="utf-8")


def main() -> int:
    try:
        conn = connexion_postgres()
    except ErreurConnexion as erreur:
        print(f"ERREUR : {erreur}", file=sys.stderr)
        return 1
    conn.autocommit = True      # chaque essai est indépendant : un échec n'en bloque pas un autre
    try:
        creer_schema(conn, SCHEMA)
        preparer_donnees(conn)
        refus = executer_refus(conn)
        comportements = executer_comportements(conn)
    finally:
        supprimer_schema(conn, SCHEMA)
        conn.close()

    ecrire(refus, comportements)
    for f in refus:
        print(f"{'OK ' if f['ok'] else 'KO '} {f['categorie']:<14} {f['obtenu']:<22} {f['contrainte']}")
    for description, _, ok in comportements:
        print(f"{'OK ' if ok else 'KO '} {description[:100]}")
    echecs = sum(not f["ok"] for f in refus) + sum(not ok for _, _, ok in comportements)
    print(f"\nÉcrit : {SORTIE} | écarts : {echecs}")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
