# Mesures 2.5, étape « apres » (schéma volume)

Cibles : client `CLI0019575`, navigation `CLI0000229` le `2026-04-15`. Lignes rendues : Q2=9, Q3=3.

| Requête | Médiane (ms) | Mesures | Lignes estimées | Lignes réelles | Tampons | Nœuds |
|---|---|---|---|---|---|---|
| Q1 SM-125 Liste 1 | 104.25 | 3 | 1 | 1 | 68766 | Aggregate > Hash Join > Seq Scan(commandes) > Hash > Seq Scan(paiements) > Index Only Scan(idx_paiements_commande) > Index Only Scan(idx_paiements_commande) |
| Q2 achats d'un client | 0.04 | 5 | 2 | 9 | 12 | Bitmap Heap Scan(commandes) > Bitmap Index Scan(idx_commandes_client) |
| Q3 navigation client/jour | 0.03 | 5 | 1 | 3 | 6 | Index Scan(idx_navigation_client_date) |

Taille des index : idx_paiements_commande = 2464 kB, idx_commandes_client = 1792 kB, idx_navigation_client_date = 13 MB

## Plan (passe à froid) : Q1 SM-125 Liste 1

```
Aggregate  (cost=191086.15..191086.16 rows=1 width=24) (actual time=109.051..109.053 rows=1 loops=1)
  Buffers: shared hit=68464 read=302
  ->  Hash Anti Join  (cost=3064.03..5129.85 rows=11018 width=12) (actual time=24.991..41.003 rows=11118 loops=1)
        Hash Cond: (c.commande_id = p.commande_id)
        Buffers: shared hit=2056
        ->  Seq Scan on commandes c  (cost=0.00..1664.76 rows=80876 width=12) (actual time=0.009..3.393 rows=80876 loops=1)
              Buffers: shared hit=856
        ->  Hash  (cost=2190.80..2190.80 rows=69858 width=12) (actual time=24.822..24.823 rows=69758 loops=1)
              Buckets: 131072  Batches: 1  Memory Usage: 4022kB
              Buffers: shared hit=1200
              ->  Seq Scan on paiements p  (cost=0.00..2190.80 rows=69858 width=12) (actual time=9.937..16.117 rows=69758 loops=1)
                    Filter: (statut_paiement = 'réussi'::text)
                    Rows Removed by Filter: 9506
                    Buffers: shared hit=1200
  SubPlan 1
    ->  Index Only Scan using idx_paiements_commande on paiements q  (cost=0.42..8.44 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=11118)
          Index Cond: (commande_id = c.commande_id)
          Heap Fetches: 0
          Buffers: shared hit=33053 read=302
  SubPlan 3
    ->  Index Only Scan using idx_paiements_commande on paiements q_1  (cost=0.42..8.44 rows=1 width=0) (actual time=0.003..0.003 rows=1 loops=11118)
          Index Cond: (commande_id = c.commande_id)
          Heap Fetches: 0
          Buffers: shared hit=33355
Planning:
  Buffers: shared hit=43 read=6
Planning Time: 0.518 ms
JIT:
  Functions: 22
  Options: Inlining false, Optimization false, Expressions true, Deforming true
  Timing: Generation 0.660 ms, Inlining 0.000 ms, Optimization 0.420 ms, Emission 9.550 ms, Total 10.631 ms
Execution Time: 130.566 ms
```

## Plan (passe à froid) : Q2 achats d'un client

```
Bitmap Heap Scan on commandes  (cost=4.43..12.17 rows=2 width=52) (actual time=0.087..0.101 rows=9 loops=1)
  Recheck Cond: (client_id = 'CLI0019575'::text)
  Heap Blocks: exact=9
  Buffers: shared hit=9 read=3
  ->  Bitmap Index Scan on idx_commandes_client  (cost=0.00..4.43 rows=2 width=0) (actual time=0.082..0.082 rows=9 loops=1)
        Index Cond: (client_id = 'CLI0019575'::text)
        Buffers: shared read=3
Planning:
  Buffers: shared hit=22
Planning Time: 0.111 ms
Execution Time: 0.124 ms
```

## Plan (passe à froid) : Q3 navigation client/jour

```
Index Scan using idx_navigation_client_date on navigation  (cost=0.42..8.44 rows=1 width=79) (actual time=0.079..0.097 rows=3 loops=1)
  Index Cond: ((client_id = 'CLI0000229'::text) AND (date_evenement >= '2026-04-15'::date) AND (date_evenement < '2026-04-16'::date))
  Buffers: shared hit=3 read=6
Planning:
  Buffers: shared hit=38
Planning Time: 0.148 ms
Execution Time: 0.109 ms
```
