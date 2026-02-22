# Database (Flyway + Seeds)

## Migrations

Flyway migrations live under `db/migration`. Example migrate command:

```bash
flyway \
  -url="jdbc:mysql://localhost:3306/bsl?useSSL=false&allowPublicKeyRetrieval=true" \
  -user=bsl -password=bsl \
  -locations=filesystem:db/migration \
  migrate
```

## KDC Seed Load (manual)

`db/seeds/kdc_seed_load.sql` loads KDC codes from a CSV into `kdc_seed_raw`,
derives `kdc_seed`/`kdc_node`, and backfills `material.kdc_node_id`.

1. Ensure `local_infile` is enabled:

```sql
SHOW VARIABLES LIKE 'local_infile';
```

2. Run the seed script (requires `--local-infile=1`):

```bash
docker exec -it mysql mysql -uroot -plocalroot -e "CREATE USER IF NOT EXISTS 'bsl'@'%' IDENTIFIED BY 'bsl'; GRANT ALL PRIVILEGES ON bsl.* TO 'bsl'@'%'; FLUSH PRIVILEGES;"
```

```bash
mysql --local-infile=1 --protocol=tcp -h 127.0.0.1 -P 3306 -u bsl -pbsl bsl < db/seeds/kdc_seed_load.sql
```
