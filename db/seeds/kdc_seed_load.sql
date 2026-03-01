-- Load KDC seed data from CSV and rebuild category/material mappings.
-- Requires MySQL local_infile=1 and:
-- mysql --local-infile=1 --protocol=tcp -h 127.0.0.1 -P 3306 -u bsl -pbsl bsl < db/seeds/kdc_seed_load.sql

TRUNCATE TABLE kdc_seed_raw;

SET @orig_sql_mode := @@SESSION.sql_mode;
SET SESSION sql_mode = REPLACE(@@SESSION.sql_mode, 'NO_BACKSLASH_ESCAPES', '');

LOAD DATA LOCAL INFILE 'db/seeds/kdc_seed_raw.csv'
INTO TABLE kdc_seed_raw
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' ESCAPED BY 0x5C
LINES TERMINATED BY 0x0D0A
(code, name);

SET SESSION sql_mode = @orig_sql_mode;

UPDATE kdc_seed_raw
SET name = TRIM(TRAILING '\r' FROM name);

TRUNCATE TABLE kdc_seed;
TRUNCATE TABLE kdc_node;

INSERT INTO kdc_seed(code, name, parent_code, depth)
SELECT
  r.code,
  r.name,
  CASE
    WHEN (CAST(r.code AS UNSIGNED) % 100) = 0 THEN NULL
    WHEN (CAST(r.code AS UNSIGNED) % 10) = 0 THEN
      LPAD(CAST((CAST(r.code AS UNSIGNED) DIV 100) * 100 AS CHAR), 3, '0')
    ELSE
      LPAD(CAST((CAST(r.code AS UNSIGNED) DIV 10) * 10 AS CHAR), 3, '0')
  END AS parent_code,
  CASE
    WHEN (CAST(r.code AS UNSIGNED) % 100) = 0 THEN 0
    WHEN (CAST(r.code AS UNSIGNED) % 10) = 0 THEN 1
    ELSE 2
  END AS depth
FROM kdc_seed_raw r
WHERE r.code REGEXP '^[0-9]{3}$'
  AND r.name IS NOT NULL
  AND TRIM(r.name) <> ''
ON DUPLICATE KEY UPDATE
  name = VALUES(name),
  parent_code = VALUES(parent_code),
  depth = VALUES(depth);

INSERT INTO kdc_node(code, name, parent_id, depth, created_at, updated_at)
SELECT s.code, s.name, NULL, s.depth, NOW(), NOW()
FROM kdc_seed s
WHERE s.depth = 0
ON DUPLICATE KEY UPDATE
  name = VALUES(name),
  depth = VALUES(depth),
  updated_at = NOW();

INSERT INTO kdc_node(code, name, parent_id, depth, created_at, updated_at)
SELECT
  c.code,
  c.name,
  p.id AS parent_id,
  c.depth,
  NOW(),
  NOW()
FROM kdc_seed c
JOIN kdc_node p ON p.code = c.parent_code
WHERE c.depth IN (1, 2)
ORDER BY c.depth ASC, c.code ASC
ON DUPLICATE KEY UPDATE
  name = VALUES(name),
  parent_id = VALUES(parent_id),
  depth = VALUES(depth),
  updated_at = NOW();

UPDATE material_kdc mk
LEFT JOIN kdc_node kn ON kn.code = mk.kdc_code_3
SET mk.kdc_node_id = kn.id;
