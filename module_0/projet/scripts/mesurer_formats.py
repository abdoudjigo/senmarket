"""
Mesures du Module 0 : machine, volume et comparaison des formats.

Écrit docs/MESURES.md et complète la décision « format » de docs/DECISIONS.md.
À relancer après toute régénération de la partition volume :
    python scripts/mesurer_formats.py --run-date 2026-11-02 --temps-generation 18.65
"""

from __future__ import annotations

import argparse
import platform
import statistics
import tempfile
import time
from datetime import date
from pathlib import Path

import pandas as pd

RACINE = Path(__file__).resolve().parents[1]
ESSAIS = 6  # la première lecture (à froid) est ignorée : il reste 5 mesures


def lire_processeur() -> str:
    """Nom du processeur, lu dans /proc/cpuinfo (Linux)."""
    try:
        for ligne in Path("/proc/cpuinfo").read_text().splitlines():
            if ligne.startswith("model name"):
                return ligne.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "inconnu"


def lire_memoire() -> str:
    """Mémoire totale, lue dans /proc/meminfo (Linux)."""
    try:
        for ligne in Path("/proc/meminfo").read_text().splitlines():
            if ligne.startswith("MemTotal"):
                return f"{int(ligne.split()[1]) / 1024 / 1024:.1f} Go"
    except OSError:
        pass
    return "inconnue"


def lire_disque() -> str:
    """SSD ou disque dur, d'après le système (0 = SSD, 1 = disque dur)."""
    try:
        for dispositif in sorted(Path("/sys/block").iterdir()):
            if dispositif.name.startswith(("loop", "ram", "zram")):
                continue
            rotatif = (dispositif / "queue" / "rotational").read_text().strip()
            return f"{'disque dur' if rotatif == '1' else 'SSD'} ({dispositif.name})"
    except OSError:
        pass
    return "à compléter (SSD ou disque dur)"


def mediane_lecture(lecteur, chemin: Path, **options) -> float:
    """Médiane de 5 lectures ; la première, à froid, n'est pas retenue."""
    durees = []
    for _ in range(ESSAIS):
        debut = time.perf_counter()
        lecteur(chemin, **options)
        durees.append(time.perf_counter() - debut)
    return statistics.median(durees[1:])


def main() -> None:
    parser = argparse.ArgumentParser(description="Mesurer machine et formats.")
    parser.add_argument("--run-date", type=date.fromisoformat, default=date(2026, 11, 2))
    parser.add_argument("--temps-generation", type=float, required=True,
                        help="Durée du pipeline sur la partition volume, en secondes.")
    args = parser.parse_args()

    dossier = RACINE / "data" / "processed" / f"date={args.run_date.isoformat()}"
    if not dossier.exists():
        raise SystemExit(
            f"Partition introuvable : {dossier}\n"
            "Génère-la d'abord : python scripts/run_pipeline.py --run-date "
            f"{args.run_date} --generer --rows 200000 --sans-tests"
        )

    lignes = pd.read_parquet(dossier / "lignes_commande.parquet")
    commandes = pd.read_parquet(dossier / "commandes.parquet")

    with tempfile.TemporaryDirectory() as nom_tmp:
        tmp = Path(nom_tmp)
        # Le JSON « tableau » n'est pas produit par le pipeline : on le fabrique ici.
        lignes.to_json(tmp / "lignes_commande.json", orient="records", date_format="iso")
        commandes.to_json(tmp / "commandes.json", orient="records", date_format="iso")

        definitions = [
            ("CSV", lambda t: dossier / f"{t}.csv", pd.read_csv, {}),
            ("JSON (tableau)", lambda t: tmp / f"{t}.json", pd.read_json, {}),
            ("JSON Lines", lambda t: dossier / "json" / f"{t}.jsonl", pd.read_json, {"lines": True}),
            ("Parquet", lambda t: dossier / f"{t}.parquet", pd.read_parquet, {}),
        ]

        lignes_tableau = []
        resultats = {}
        for nom, chemin_de, lecteur, options in definitions:
            chemin = chemin_de("lignes_commande")
            if not chemin.exists():
                raise SystemExit(f"Fichier introuvable : {chemin}")
            temps = mediane_lecture(lecteur, chemin, **options)
            taille = chemin.stat().st_size / 1024 ** 2
            type_date = str(lecteur(chemin_de("commandes"), **options)["date_commande"].dtype)
            resultats[nom] = (temps, taille)
            lignes_tableau.append(f"| {nom} | {temps:.3f} | {taille:.1f} | {type_date} |")

    # Lecture par morceaux : le résultat doit être identique à la lecture complète.
    csv = dossier / "lignes_commande.csv"
    complet = pd.read_csv(csv)
    morceaux = pd.concat(pd.read_csv(csv, chunksize=50_000), ignore_index=True)
    identique = complet.equals(morceaux)

    temps_csv, taille_csv = resultats["CSV"]
    temps_parquet, taille_parquet = resultats["Parquet"]
    vitesse = temps_csv / temps_parquet
    poids = taille_csv / taille_parquet

    contenu = f"""# Mesures du Module 0

Ces chiffres décrivent ma machine et mes données : ils ne sont comparables qu'à eux-mêmes. Ils sont régénérés par `python scripts/mesurer_formats.py`.

## Machine

- Processeur : {lire_processeur()}
- Mémoire : {lire_memoire()}
- Disque : {lire_disque()}
- Python : {platform.python_version()}
- Système : {platform.platform()}

## Partition volume

- Partition : `date={args.run_date.isoformat()}`, générée avec `--rows 200000` et six défauts injectés
- Lignes de commande acceptées : {len(lignes):,}
- Temps du pipeline (génération, nettoyage, export, analyse, graphiques ; sans les tests) : {args.temps_generation:.2f} s, mesuré avec `time`

## Formats (table `lignes_commande`)

Temps de lecture = médiane de 5 mesures, la première (à froid) ignorée. La dernière colonne donne le type obtenu pour `date_commande` en lisant la table `commandes` dans chaque format.

| Format | Lecture (s) | Taille (Mo) | Type de `date_commande` |
|---|---:|---:|---|
{chr(10).join(lignes_tableau)}

## Lecture par morceaux

`read_csv(chunksize=50_000)` donne le même résultat que la lecture complète : **{identique}**.

## Conclusion

Sur cette machine, le Parquet se lit **{vitesse:.1f} fois plus vite** que le CSV et pèse **{poids:.1f} fois moins**, tout en conservant les types. Le CSV reste utile pour lire à l'œil, le JSON Lines pour l'ingestion en flux.
""".replace("{lignes:,}", "")
    contenu = contenu.replace(f"{len(lignes):,}", f"{len(lignes):,}".replace(",", " "))

    (RACINE / "docs").mkdir(exist_ok=True)
    (RACINE / "docs" / "MESURES.md").write_text(contenu, encoding="utf-8")

    # La décision « format » s'appuie maintenant sur une mesure.
    chemin_decisions = RACINE / "docs" / "DECISIONS.md"
    ancien = "*(Compléter avec tes mesures de temps et de taille sur 200 000 lignes avant de défendre ce choix.)*"
    nouveau = (
        f"*(Mesuré sur {len(lignes):,} lignes de `lignes_commande`".replace(",", " ")
        + f" : le Parquet se lit {vitesse:.1f} fois plus vite que le CSV et pèse {poids:.1f} fois moins ;"
        " détails dans `MESURES.md`.)*"
    )
    if chemin_decisions.exists():
        texte = chemin_decisions.read_text(encoding="utf-8")
        if ancien in texte:
            chemin_decisions.write_text(texte.replace(ancien, nouveau, 1), encoding="utf-8")
            print("DECISIONS.md complété avec les mesures.")
        else:
            print("DECISIONS.md : mention à compléter introuvable (déjà remplie ?).")

    print(f"MESURES.md écrit. Parquet : {vitesse:.1f}x plus rapide, {poids:.1f}x plus léger que le CSV.")


if __name__ == "__main__":
    main()
