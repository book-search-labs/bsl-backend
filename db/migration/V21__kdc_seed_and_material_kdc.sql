-- KDC seed tables + material kdc mapping

CREATE TABLE IF NOT EXISTS kdc_seed_raw (
  code VARCHAR(16)  NOT NULL,
  name VARCHAR(255) NOT NULL,
  PRIMARY KEY (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS kdc_seed (
  code        VARCHAR(16)  NOT NULL,
  name        VARCHAR(255) NOT NULL,
  parent_code VARCHAR(16)  NULL,
  depth       INT          NOT NULL,
  PRIMARY KEY (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS kdc_node (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  code VARCHAR(16) NOT NULL,
  name VARCHAR(255) NOT NULL,
  parent_id BIGINT NULL,
  depth INT NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY ux_kdc_node_code (code),
  INDEX idx_kdc_node_parent_id (parent_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS material_kdc (
                                          material_id   VARCHAR(64) NOT NULL,
  kdc_code_raw  VARCHAR(64) NOT NULL,   -- 예: 692.57
  kdc_code_3    CHAR(3) NOT NULL,       -- 예: '692' (대분류)
  kdc_node_id   BIGINT NULL,            -- 매핑 결과
  ord           INT NOT NULL DEFAULT 0, -- 배열 순서(0-base)
  is_primary    TINYINT(1) NOT NULL DEFAULT 0, -- ord=0을 주분류로
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

  PRIMARY KEY (material_id, kdc_code_raw),
  KEY idx_mk_kdc3 (kdc_code_3),
  KEY idx_mk_node (kdc_node_id)
  ) ENGINE=InnoDB;




TRUNCATE TABLE kdc_seed;

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

-- Insert root nodes (depth = 0)
INSERT INTO kdc_node(code, name, parent_id, depth, created_at, updated_at)
SELECT s.code, s.name, NULL, s.depth, NOW(), NOW()
FROM kdc_seed s
WHERE s.depth = 0
  ON DUPLICATE KEY UPDATE
                     name = VALUES(name),
                     depth = VALUES(depth),
                     updated_at = NOW();

-- Insert depth 1/2 nodes (parents first)
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

INSERT INTO material_kdc (material_id, kdc_code_raw, kdc_code_3, ord, is_primary)
SELECT
  m.material_id,
  jt.kdc_code_raw,
  LPAD(SUBSTRING_INDEX(jt.kdc_code_raw, '.', 1), 3, '0') AS kdc_code_3,
  (jt.ord - 1) AS ord,  -- JSON_TABLE ORDINALITY는 1-base라 0-base로 보정
  CASE WHEN (jt.ord - 1) = 0 THEN 1 ELSE 0 END AS is_primary
FROM material m
       JOIN JSON_TABLE(
  JSON_EXTRACT(m.raw_payload, '$.kdc'),
  '$[*]' COLUMNS (
    ord FOR ORDINALITY,
    kdc_code_raw VARCHAR(64) PATH '$'
  )
            ) jt
WHERE JSON_TYPE(JSON_EXTRACT(m.raw_payload, '$.kdc')) = 'ARRAY'
  AND jt.kdc_code_raw REGEXP '^[0-9]{3}(\\.[0-9]+)?$'
ON DUPLICATE KEY UPDATE
                   ord = VALUES(ord),
                   is_primary = VALUES(is_primary);


INSERT INTO material_kdc (material_id, kdc_code_raw, kdc_code_3, ord, is_primary)
SELECT
  m.material_id,
  JSON_UNQUOTE(JSON_EXTRACT(m.raw_payload, '$.kdc')) AS kdc_code_raw,
  LPAD(SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(m.raw_payload, '$.kdc')), '.', 1), 3, '0') AS kdc_code_3,
  0 AS ord,
  1 AS is_primary
FROM material m
WHERE JSON_TYPE(JSON_EXTRACT(m.raw_payload, '$.kdc')) = 'STRING'
  AND JSON_UNQUOTE(JSON_EXTRACT(m.raw_payload, '$.kdc'))
  REGEXP '^[0-9]{3}(\\.[0-9]+)?$'
ON DUPLICATE KEY UPDATE
                   is_primary = 1;

INSERT INTO material_kdc (material_id, kdc_code_raw, kdc_code_3, ord, is_primary)
SELECT
  m.material_id,
  CAST(JSON_EXTRACT(m.raw_payload, '$.kdc') AS CHAR) AS kdc_code_raw,
  LPAD(SUBSTRING_INDEX(CAST(JSON_EXTRACT(m.raw_payload, '$.kdc') AS CHAR), '.', 1), 3, '0') AS kdc_code_3,
  0 AS ord,
  1 AS is_primary
FROM material m
WHERE JSON_TYPE(JSON_EXTRACT(m.raw_payload, '$.kdc')) IN ('INTEGER', 'DOUBLE')
  AND CAST(JSON_EXTRACT(m.raw_payload, '$.kdc') AS CHAR)
  REGEXP '^[0-9]{3}(\\.[0-9]+)?$'
ON DUPLICATE KEY UPDATE
                   is_primary = 1;
