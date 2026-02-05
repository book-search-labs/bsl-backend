-- Load KDC seed data from CSV into kdc_seed_raw
-- Update the CSV path to your environment before running.

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
