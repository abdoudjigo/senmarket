#!/bin/bash
# Start the bases, create the schemas if missing, load everything. Safe to run again.
set -euo pipefail
cd "$(dirname "$0")"
DC="docker compose --env-file .env -f infra/docker-compose.yml"

$DC up -d
for _ in $(seq 1 60); do
  [ "$($DC ps --format '{{.Status}}' | grep -c healthy)" -ge 3 ] && break
  sleep 2
done

for s in principal volume; do
  existe=$($DC exec -T postgres sh -c "psql -U \$POSTGRES_USER -d \$POSTGRES_DB -tA -c \"SELECT count(*) FROM information_schema.schemata WHERE schema_name='$s'\"")
  if [ "$existe" = "0" ]; then
    echo "création du schéma $s"
    $DC exec -T postgres sh -c "psql -U \$POSTGRES_USER -d \$POSTGRES_DB -v schema=$s -v ON_ERROR_STOP=1" < sql/01_schema.sql > /dev/null
  fi
done

python -m senmarket_bases.charger_postgres --run-date 2026-10-29 --schema principal | tail -2
python -m senmarket_bases.charger_postgres --run-date 2026-11-02 --schema volume | tail -2
python -m senmarket_bases.charger_mongo 2026-10-29 | head -1

#cd ~/Documents/"Orange Digital center"/Parcours/senmarket/module_1
#docker compose --env-file .env -f infra/docker-compose.yml down -v
#./demarrer.sh