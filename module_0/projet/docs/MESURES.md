# Mesures du Module 0

Ces chiffres décrivent ma machine et mes données : ils ne sont comparables qu'à eux-mêmes. Ils sont régénérés par `python scripts/mesurer_formats.py`.

## Machine

- Processeur : 13th Gen Intel(R) Core(TM) i7-1355U
- Mémoire : 14.8 Go
- Disque : SSD (nvme0n1)
- Python : 3.14.4
- Système : Linux-7.0.0-38-generic-x86_64-inconnu-with-glibc2.43

## Partition volume

- Partition : `date=2026-11-02`, générée avec `--rows 200000` et six défauts injectés
- Lignes de commande acceptées : 199 997
- Temps du pipeline (génération, nettoyage, export, analyse, graphiques ; sans les tests) : 18.65 s, mesuré avec `time`

## Formats (table `lignes_commande`)

Temps de lecture = médiane de 5 mesures, la première (à froid) ignorée. La dernière colonne donne le type obtenu pour `date_commande` en lisant la table `commandes` dans chaque format.

| Format | Lecture (s) | Taille (Mo) | Type de `date_commande` |
|---|---:|---:|---|
| CSV | 0.026 | 8.4 | str |
| JSON (tableau) | 0.598 | 27.5 | str |
| JSON Lines | 0.698 | 27.5 | str |
| Parquet | 0.025 | 3.2 | datetime64[us] |

## Lecture par morceaux

`read_csv(chunksize=50_000)` donne le même résultat que la lecture complète : **True**.

## Conclusion

Sur cette machine, le Parquet se lit **1.0 fois plus vite** que le CSV et pèse **2.6 fois moins**, tout en conservant les types. Le CSV reste utile pour lire à l'œil, le JSON Lines pour l'ingestion en flux.
