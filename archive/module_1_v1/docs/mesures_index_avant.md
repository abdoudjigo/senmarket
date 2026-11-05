# Mesures 2.5, étape « avant » (schéma volume)

Cibles : client `CLI0019575`, navigation `CLI0000229` le `2026-04-15`. Lignes rendues : Q2=9, Q3=3.

| Requête | Médiane (ms) | Mesures | Lignes estimées | Lignes réelles | Tampons | Nœuds |
|---|---|---|---|---|---|---|
| Q1 SM-125 Liste 1 | 34078.04 | 3 | 1 | 1 | 14971542 | Aggregate > Hash Join > Seq Scan(commandes) > Hash > Seq Scan(paiements) > Seq Scan(paiements) > Seq Scan(paiements) |
| Q2 achats d'un client | 6.98 | 5 | 2 | 9 | 856 | Seq Scan(commandes) |
| Q3 navigation client/jour | 32.36 | 5 | 1 | 3 | 5360 | Gather > Seq Scan(navigation) |

## Plan (passe à froid) : Q1 SM-125 Liste 1

```
Aggregate  (cost=49171146.88..49171146.89 rows=1 width=24) (actual time=32743.961..32743.964 rows=1 loops=1)
  Buffers: shared hit=14970342 read=1200
  ->  Hash Anti Join  (cost=3061.49..5129.12 rows=11221 width=12) (actual time=158.915..188.612 rows=11118 loops=1)
        Hash Cond: (c.commande_id = p.commande_id)
        Buffers: shared hit=856 read=1200
        ->  Seq Scan on commandes c  (cost=0.00..1664.76 rows=80876 width=12) (actual time=0.023..5.499 rows=80876 loops=1)
              Buffers: shared hit=856
        ->  Hash  (cost=2190.80..2190.80 rows=69655 width=12) (actual time=158.686..158.687 rows=69758 loops=1)
              Buckets: 131072  Batches: 1  Memory Usage: 4022kB
              Buffers: shared read=1200
              ->  Seq Scan on paiements p  (cost=0.00..2190.80 rows=69655 width=12) (actual time=140.317..149.851 rows=69758 loops=1)
                    Filter: (statut_paiement = 'réussi'::text)
                    Rows Removed by Filter: 9506
                    Buffers: shared read=1200
  SubPlan 1
    ->  Seq Scan on paiements q  (cost=0.00..2190.80 rows=1 width=0) (actual time=1.470..1.470 rows=1 loops=11118)
          Filter: (commande_id = c.commande_id)
          Rows Removed by Filter: 45222
          Buffers: shared hit=7484743
  SubPlan 3
    ->  Seq Scan on paiements q_1  (cost=0.00..2190.80 rows=1 width=0) (actual time=1.456..1.456 rows=1 loops=11118)
          Filter: (commande_id = c.commande_id)
          Rows Removed by Filter: 45222
          Buffers: shared hit=7484743
Planning:
  Buffers: shared hit=35 read=7
Planning Time: 1.334 ms
JIT:
  Functions: 22
  Options: Inlining true, Optimization true, Expressions true, Deforming true
  Timing: Generation 1.673 ms, Inlining 49.759 ms, Optimization 51.473 ms, Emission 39.047 ms, Total 141.951 ms
Execution Time: 32909.955 ms
```

## Plan (passe à froid) : Q2 achats d'un client

```
Seq Scan on commandes  (cost=0.00..1866.95 rows=2 width=52) (actual time=1.577..7.063 rows=9 loops=1)
  Filter: (client_id = 'CLI0019575'::text)
  Rows Removed by Filter: 80867
  Buffers: shared hit=856
Planning:
  Buffers: shared hit=18
Planning Time: 0.111 ms
Execution Time: 7.231 ms
```

## Plan (passe à froid) : Q3 navigation client/jour

```
Gather  (cost=1000.00..9276.77 rows=1 width=79) (actual time=14.357..68.353 rows=3 loops=1)
  Workers Planned: 2
  Workers Launched: 2
  Buffers: shared hit=32 read=5328
  ->  Parallel Seq Scan on navigation  (cost=0.00..8276.67 rows=1 width=79) (actual time=4.584..14.368 rows=1 loops=3)
        Filter: ((date_evenement >= '2026-04-15'::date) AND (date_evenement < '2026-04-16'::date) AND (client_id = 'CLI0000229'::text))
        Rows Removed by Filter: 133332
        Buffers: shared hit=32 read=5328
Planning:
  Buffers: shared hit=34
Planning Time: 0.198 ms
Execution Time: 68.382 ms
```
