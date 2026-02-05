/* ============================================================
   NLK raw_node -> canonical inserts (MySQL 8)
   - sameAs skipped
   - Person + Organization => agent
   - Library => library (NOT agent)
   - Material + identifiers + links
   ============================================================ */

-- ------------------------------------------------------------
-- 0) Concept
-- ------------------------------------------------------------
INSERT IGNORE INTO concept (
  concept_id,
  pref_label,
  label,
  broader_concept_id,
  scheme_id,
  raw_payload,
  last_raw_id,
  last_payload_hash,
  created_at,
  updated_at
)
SELECT
  jt.concept_id,
  NULLIF(jt.pref_label, '') AS pref_label,
  NULLIF(jt.label, '')      AS label,
  NULLIF(jt.broader, '')    AS broader_concept_id,
  NULLIF(jt.in_scheme, '')  AS scheme_id,
  jt.node_json              AS raw_payload,
  r.raw_id                  AS last_raw_id,
  r.payload_hash            AS last_payload_hash,
  NOW(),
  NOW()
FROM raw_node r
       JOIN JSON_TABLE(
  r.payload,
  '$'
    COLUMNS (
    node_json   JSON        PATH '$',
    concept_id  VARCHAR(64) PATH '$."@id"',
    pref_label  VARCHAR(512) PATH '$.prefLabel' NULL ON EMPTY NULL ON ERROR,
    label       VARCHAR(512) PATH '$.label'     NULL ON EMPTY NULL ON ERROR,
    broader     VARCHAR(64)  PATH '$.broader'   NULL ON EMPTY NULL ON ERROR,
    in_scheme   VARCHAR(64)  PATH '$.inScheme'  NULL ON EMPTY NULL ON ERROR
  )
            ) jt
WHERE r.entity_kind = 'CONCEPT'
  AND jt.concept_id IS NOT NULL
  AND jt.concept_id <> ''
  ON DUPLICATE KEY UPDATE
                     pref_label        = VALUES(pref_label),
                     label             = VALUES(label),
                     broader_concept_id= VALUES(broader_concept_id),
                     scheme_id         = VALUES(scheme_id),
                     raw_payload       = VALUES(raw_payload),
                     last_raw_id       = VALUES(last_raw_id),
                     last_payload_hash = VALUES(last_payload_hash),
                     updated_at        = NOW();


-- ------------------------------------------------------------
-- 1) Agent (Person + Organization)  -- @type = nlon:Author
--    - agent_type: If rdf:type includes /Person, classify as PERSON; otherwise, classify as ORG.
--    - Exclude Library (@type = nlon:Library).
-- ------------------------------------------------------------

INSERT IGNORE INTO agent (
  agent_id,
  agent_type,                 -- 'PERSON' | 'ORG'
  pref_label,
  label,
  name,
  isni,
  url,
  location,
  gender,
  birth_year,
  death_year,
  corporate_name,
  job_title,
  date_of_establishment,      -- org only
  date_published,
  modified_at,
  field_of_activity_json,
  source_json,
  raw_payload,
  last_raw_id,
  last_payload_hash,
  created_at,
  updated_at
)
SELECT
  JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$."@id"')) AS agent_id,

  CASE
    WHEN (
      (JSON_TYPE(JSON_EXTRACT(r.payload, '$."rdf:type"')) = 'STRING'
        AND JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$."rdf:type"')) LIKE '%/Person%')
        OR
      (JSON_TYPE(JSON_EXTRACT(r.payload, '$."rdf:type"')) = 'ARRAY'
        AND JSON_SEARCH(JSON_EXTRACT(r.payload, '$."rdf:type"'), 'one', '%/Person%') IS NOT NULL)
      )
      THEN 'PERSON' ELSE 'ORG'
    END AS agent_type,

  JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.prefLabel')) AS pref_label,
  JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.label')) AS label,
  JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.name')) AS name,
  JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.isni')) AS isni,
  JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.url')) AS url,

  COALESCE(
    JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.location')),
    JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$."schema:location"'))
  ) AS location,

  JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.gender')) AS gender,

  -- birthYear / deathYear: "1975^^http://www.w3.org/2001/XMLSchema#int"
  CASE
    WHEN JSON_EXTRACT(r.payload, '$.birthYear') IS NULL THEN NULL
    ELSE CAST(SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.birthYear')), '^^', 1) AS UNSIGNED)
    END AS birth_year,
  CASE
    WHEN JSON_EXTRACT(r.payload, '$.deathYear') IS NULL THEN NULL
    ELSE CAST(SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.deathYear')), '^^', 1) AS UNSIGNED)
    END AS death_year,

  JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.corporateName')) AS corporate_name,

  CASE
    WHEN JSON_TYPE(JSON_EXTRACT(r.payload, '$.jobTitle'))='ARRAY'
      THEN JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.jobTitle[0]'))
    WHEN JSON_TYPE(JSON_EXTRACT(r.payload, '$.jobTitle'))='STRING'
      THEN JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.jobTitle'))
    ELSE NULL
    END AS job_title,

  CASE
    WHEN JSON_EXTRACT(r.payload, '$.dateOfEstablishment') IS NULL THEN NULL
    ELSE
      CASE
        WHEN JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.dateOfEstablishment'))
          REGEXP '^[0-9]{4}(0[1-9]|1[0-2])(0[1-9]|[12][0-9]|3[01])$'
            THEN STR_TO_DATE(JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.dateOfEstablishment')), '%Y%m%d')

        WHEN JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.dateOfEstablishment'))
          REGEXP '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
            THEN STR_TO_DATE(JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.dateOfEstablishment')), '%Y-%m-%d')

        WHEN JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.dateOfEstablishment'))
          REGEXP '^[0-9]{4}/[0-9]{2}/[0-9]{2}$'
            THEN STR_TO_DATE(JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.dateOfEstablishment')), '%Y/%m/%d')

        WHEN JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.dateOfEstablishment'))
          REGEXP '^[0-9]{4}\\.[0-9]{1,2}\\.$'
            THEN STR_TO_DATE(
          CONCAT(
            SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.dateOfEstablishment')), '.', 1),
            '-',
            LPAD(SUBSTRING_INDEX(SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.dateOfEstablishment')), '.', 2), '.', -1), 2, '0'),
            '-01'
          ),
          '%Y-%m-%d'
                 )

        WHEN JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.dateOfEstablishment'))
          REGEXP '^[0-9]{4}\\.[0-9]{1,2}\\.[0-9]{1,2}\\.$'
            THEN STR_TO_DATE(
          CONCAT(
            SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.dateOfEstablishment')), '.', 1),
            '-',
            LPAD(SUBSTRING_INDEX(SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.dateOfEstablishment')), '.', 2), '.', -1), 2, '0'),
            '-',
            LPAD(SUBSTRING_INDEX(SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.dateOfEstablishment')), '.', 3), '.', -1), 2, '0')
          ),
          '%Y-%m-%d'
                 )

        WHEN JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.dateOfEstablishment')) REGEXP '^[0-9]{4}$'
            THEN STR_TO_DATE(CONCAT(JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.dateOfEstablishment')), '-01-01'), '%Y-%m-%d')

        ELSE NULL
        END
    END AS date_of_establishment,

  CASE
    WHEN JSON_EXTRACT(r.payload, '$.datePublished') IS NULL THEN NULL
    ELSE
      CASE
        WHEN SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.datePublished')), '^^', 1)
          REGEXP '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}$'
          THEN STR_TO_DATE(
          SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.datePublished')), '^^', 1),
          '%Y-%m-%dT%H:%i:%s'
               )
        WHEN SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.datePublished')), '^^', 1)
          REGEXP '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
          THEN STR_TO_DATE(
          SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.datePublished')), '^^', 1),
          '%Y-%m-%d'
               )
        ELSE NULL
        END
    END AS date_published,

  CASE
    WHEN JSON_EXTRACT(r.payload, '$.modified') IS NULL THEN NULL
    ELSE
      CASE
        WHEN SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.modified')), '^^', 1)
          REGEXP '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}$'
          THEN STR_TO_DATE(
          SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.modified')), '^^', 1),
          '%Y-%m-%dT%H:%i:%s'
               )
        WHEN SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.modified')), '^^', 1)
          REGEXP '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
          THEN STR_TO_DATE(
          SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.modified')), '^^', 1),
          '%Y-%m-%d'
               )
        ELSE NULL
        END
    END AS modified_at,

  JSON_EXTRACT(r.payload, '$.fieldOfActivity') AS field_of_activity_json,
  JSON_EXTRACT(r.payload, '$.source') AS source_json,

  r.payload AS raw_payload,
  r.raw_id,
  r.payload_hash,
  NOW(),
  NOW()
FROM raw_node r
WHERE r.entity_kind = 'AGENT'
  AND JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$."@type"')) = 'nlon:Author'
  ON DUPLICATE KEY UPDATE
                     agent_type = VALUES(agent_type),
                     pref_label = VALUES(pref_label),
                     label = VALUES(label),
                     name = VALUES(name),
                     isni = VALUES(isni),
                     url = VALUES(url),
                     location = VALUES(location),
                     gender = VALUES(gender),
                     birth_year = VALUES(birth_year),
                     death_year = VALUES(death_year),
                     corporate_name = VALUES(corporate_name),
                     job_title = VALUES(job_title),
                     date_of_establishment = VALUES(date_of_establishment),
                     date_published = VALUES(date_published),
                     modified_at = VALUES(modified_at),
                     field_of_activity_json = VALUES(field_of_activity_json),
                     source_json = VALUES(source_json),
                     raw_payload = VALUES(raw_payload),
                     last_raw_id = VALUES(last_raw_id),
                     last_payload_hash = VALUES(last_payload_hash),
                     updated_at = NOW();


-- ------------------------------------------------------------
-- 2) Agent altLabel (handle string/array variants) - optional
-- ------------------------------------------------------------
INSERT IGNORE INTO agent_alt_label (agent_id, alt_label)
SELECT
  a.agent_id,
  jt.alt_label
FROM raw_node r
       JOIN (
  SELECT JSON_UNQUOTE(JSON_EXTRACT(payload, '$."@id"')) AS agent_id, payload
  FROM raw_node
  WHERE entity_kind='AGENT'
    -- AND batch_id=@batch_id
    AND JSON_UNQUOTE(JSON_EXTRACT(payload, '$."@type"'))='nlon:Author'
) a ON a.agent_id = JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$."@id"'))
       JOIN JSON_TABLE(
  CASE
    WHEN JSON_TYPE(JSON_EXTRACT(a.payload,'$.altLabel'))='ARRAY' THEN JSON_EXTRACT(a.payload,'$.altLabel')
    WHEN JSON_TYPE(JSON_EXTRACT(a.payload,'$.altLabel'))='STRING' THEN JSON_ARRAY(JSON_UNQUOTE(JSON_EXTRACT(a.payload,'$.altLabel')))
    ELSE JSON_ARRAY()
    END,
  '$[*]' COLUMNS(alt_label VARCHAR(512) PATH '$')
            ) jt
WHERE r.entity_kind='AGENT'
  -- AND r.batch_id=@batch_id
  AND JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$."@type"'))='nlon:Author'
  AND jt.alt_label IS NOT NULL
  AND jt.alt_label <> '';


-- ------------------------------------------------------------
-- 3) Agent associatedLanguage (handle string/array variants) - optional
-- ------------------------------------------------------------
INSERT IGNORE INTO agent_language (agent_id, language)
SELECT
  a.agent_id,
  jt.lang
FROM raw_node r
       JOIN (
  SELECT JSON_UNQUOTE(JSON_EXTRACT(payload, '$."@id"')) AS agent_id, payload
  FROM raw_node
  WHERE entity_kind='AGENT'
    -- AND batch_id=@batch_id
    AND JSON_UNQUOTE(JSON_EXTRACT(payload, '$."@type"'))='nlon:Author'
) a ON a.agent_id = JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$."@id"'))
       JOIN JSON_TABLE(
  CASE
    WHEN JSON_TYPE(JSON_EXTRACT(a.payload,'$.associatedLanguage'))='ARRAY' THEN JSON_EXTRACT(a.payload,'$.associatedLanguage')
    WHEN JSON_TYPE(JSON_EXTRACT(a.payload,'$.associatedLanguage'))='STRING' THEN JSON_ARRAY(JSON_UNQUOTE(JSON_EXTRACT(a.payload,'$.associatedLanguage')))
    ELSE JSON_ARRAY()
    END,
  '$[*]' COLUMNS(lang VARCHAR(64) PATH '$')
            ) jt
WHERE r.entity_kind='AGENT'
  -- AND r.batch_id=@batch_id
  AND JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$."@type"'))='nlon:Author'
  AND jt.lang IS NOT NULL
  AND jt.lang <> '';


-- ------------------------------------------------------------
-- 4) Library (NOT an agent)
--    Even if raw_node.entity_kind is AGENT, if @type = 'nlon:Library', split it out here.
-- ------------------------------------------------------------
INSERT INTO library (
  library_id,
  identifier,
  label,
  keyword,
  library_type,
  opening_year,
  date_of_opening,
  is_closed,
  date_of_closed,
  summer_open_time,
  winter_open_time,
  fax_number,
  phone,
  location_uri,
  homepage_json,
  subject,
  raw_payload,
  last_raw_id,
  last_payload_hash,
  created_at,
  updated_at
)
SELECT
  x.library_id,
  x.identifier,
  x.label,
  x.keyword,
  x.library_type,
  x.opening_year,

  /* dateOfOpening: YYYY/MM/DD | YYYY-MM-DD | YYYYMMDD
     - If invalid (e.g., month=23, 20150229), set to NULL
     - Do not use STR_TO_DATE
  */
  CASE
    WHEN x.opening_raw IS NULL OR x.opening_raw = '' THEN NULL

    /* YYYY/MM/DD */
    WHEN x.opening_raw REGEXP '^[0-9]{4}/[0-9]{2}/[0-9]{2}$' THEN
      CASE
        WHEN
        YEAR(
      DATE_ADD(
      DATE_ADD(MAKEDATE(CAST(SUBSTRING(x.opening_raw,1,4) AS UNSIGNED),1),
      INTERVAL (CAST(SUBSTRING(x.opening_raw,6,2) AS UNSIGNED)-1) MONTH),
      INTERVAL (CAST(SUBSTRING(x.opening_raw,9,2) AS UNSIGNED)-1) DAY
      )
  ) = CAST(SUBSTRING(x.opening_raw,1,4) AS UNSIGNED)
          AND MONTH(
            DATE_ADD(
              DATE_ADD(MAKEDATE(CAST(SUBSTRING(x.opening_raw,1,4) AS UNSIGNED),1),
                       INTERVAL (CAST(SUBSTRING(x.opening_raw,6,2) AS UNSIGNED)-1) MONTH),
              INTERVAL (CAST(SUBSTRING(x.opening_raw,9,2) AS UNSIGNED)-1) DAY
            )
          ) = CAST(SUBSTRING(x.opening_raw,6,2) AS UNSIGNED)
          AND DAY(
            DATE_ADD(
              DATE_ADD(MAKEDATE(CAST(SUBSTRING(x.opening_raw,1,4) AS UNSIGNED),1),
                       INTERVAL (CAST(SUBSTRING(x.opening_raw,6,2) AS UNSIGNED)-1) MONTH),
              INTERVAL (CAST(SUBSTRING(x.opening_raw,9,2) AS UNSIGNED)-1) DAY
            )
          ) = CAST(SUBSTRING(x.opening_raw,9,2) AS UNSIGNED)
        THEN
          DATE_ADD(
            DATE_ADD(MAKEDATE(CAST(SUBSTRING(x.opening_raw,1,4) AS UNSIGNED),1),
                     INTERVAL (CAST(SUBSTRING(x.opening_raw,6,2) AS UNSIGNED)-1) MONTH),
            INTERVAL (CAST(SUBSTRING(x.opening_raw,9,2) AS UNSIGNED)-1) DAY
          )
        ELSE NULL
END

    /* YYYY-MM-DD */
WHEN x.opening_raw REGEXP '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN
      CASE
        WHEN
          YEAR(
            DATE_ADD(
              DATE_ADD(MAKEDATE(CAST(SUBSTRING(x.opening_raw,1,4) AS UNSIGNED),1),
                       INTERVAL (CAST(SUBSTRING(x.opening_raw,6,2) AS UNSIGNED)-1) MONTH),
              INTERVAL (CAST(SUBSTRING(x.opening_raw,9,2) AS UNSIGNED)-1) DAY
            )
          ) = CAST(SUBSTRING(x.opening_raw,1,4) AS UNSIGNED)
          AND MONTH(
            DATE_ADD(
              DATE_ADD(MAKEDATE(CAST(SUBSTRING(x.opening_raw,1,4) AS UNSIGNED),1),
                       INTERVAL (CAST(SUBSTRING(x.opening_raw,6,2) AS UNSIGNED)-1) MONTH),
              INTERVAL (CAST(SUBSTRING(x.opening_raw,9,2) AS UNSIGNED)-1) DAY
            )
          ) = CAST(SUBSTRING(x.opening_raw,6,2) AS UNSIGNED)
          AND DAY(
            DATE_ADD(
              DATE_ADD(MAKEDATE(CAST(SUBSTRING(x.opening_raw,1,4) AS UNSIGNED),1),
                       INTERVAL (CAST(SUBSTRING(x.opening_raw,6,2) AS UNSIGNED)-1) MONTH),
              INTERVAL (CAST(SUBSTRING(x.opening_raw,9,2) AS UNSIGNED)-1) DAY
            )
          ) = CAST(SUBSTRING(x.opening_raw,9,2) AS UNSIGNED)
        THEN
          DATE_ADD(
            DATE_ADD(MAKEDATE(CAST(SUBSTRING(x.opening_raw,1,4) AS UNSIGNED),1),
                     INTERVAL (CAST(SUBSTRING(x.opening_raw,6,2) AS UNSIGNED)-1) MONTH),
            INTERVAL (CAST(SUBSTRING(x.opening_raw,9,2) AS UNSIGNED)-1) DAY
          )
        ELSE NULL
END

    /* YYYYMMDD */
WHEN x.opening_raw REGEXP '^[0-9]{8}$' THEN
      CASE
        WHEN
          YEAR(
            DATE_ADD(
              DATE_ADD(MAKEDATE(CAST(SUBSTRING(x.opening_raw,1,4) AS UNSIGNED),1),
                       INTERVAL (CAST(SUBSTRING(x.opening_raw,5,2) AS UNSIGNED)-1) MONTH),
              INTERVAL (CAST(SUBSTRING(x.opening_raw,7,2) AS UNSIGNED)-1) DAY
            )
          ) = CAST(SUBSTRING(x.opening_raw,1,4) AS UNSIGNED)
          AND MONTH(
            DATE_ADD(
              DATE_ADD(MAKEDATE(CAST(SUBSTRING(x.opening_raw,1,4) AS UNSIGNED),1),
                       INTERVAL (CAST(SUBSTRING(x.opening_raw,5,2) AS UNSIGNED)-1) MONTH),
              INTERVAL (CAST(SUBSTRING(x.opening_raw,7,2) AS UNSIGNED)-1) DAY
            )
          ) = CAST(SUBSTRING(x.opening_raw,5,2) AS UNSIGNED)
          AND DAY(
            DATE_ADD(
              DATE_ADD(MAKEDATE(CAST(SUBSTRING(x.opening_raw,1,4) AS UNSIGNED),1),
                       INTERVAL (CAST(SUBSTRING(x.opening_raw,5,2) AS UNSIGNED)-1) MONTH),
              INTERVAL (CAST(SUBSTRING(x.opening_raw,7,2) AS UNSIGNED)-1) DAY
            )
          ) = CAST(SUBSTRING(x.opening_raw,7,2) AS UNSIGNED)
        THEN
          DATE_ADD(
            DATE_ADD(MAKEDATE(CAST(SUBSTRING(x.opening_raw,1,4) AS UNSIGNED),1),
                     INTERVAL (CAST(SUBSTRING(x.opening_raw,5,2) AS UNSIGNED)-1) MONTH),
            INTERVAL (CAST(SUBSTRING(x.opening_raw,7,2) AS UNSIGNED)-1) DAY
          )
        ELSE NULL
END

ELSE NULL
END AS date_of_opening,

  x.is_closed,
  x.date_of_closed,
  x.summer_open_time,
  x.winter_open_time,
  x.fax_number,
  x.phone,
  x.location_uri,
  x.homepage_json,
  x.subject,

  x.raw_payload,
  x.last_raw_id,
  x.last_payload_hash,
  NOW(),
  NOW()
FROM (
  SELECT
    JSON_UNQUOTE(JSON_EXTRACT(r.payload,'$."@id"')) AS library_id,
    JSON_UNQUOTE(JSON_EXTRACT(r.payload,'$.identifier')) AS identifier,
    JSON_UNQUOTE(JSON_EXTRACT(r.payload,'$.label')) AS label,
    JSON_UNQUOTE(JSON_EXTRACT(r.payload,'$.keyword')) AS keyword,
    JSON_UNQUOTE(JSON_EXTRACT(r.payload,'$.libraryType')) AS library_type,
    CAST(JSON_UNQUOTE(JSON_EXTRACT(r.payload,'$.openingYear')) AS UNSIGNED) AS opening_year,
    JSON_UNQUOTE(JSON_EXTRACT(r.payload,'$.dateOfOpening')) AS opening_raw,

    CASE
      WHEN JSON_EXTRACT(r.payload,'$.isClosed') IS NULL THEN NULL
      WHEN LOWER(JSON_UNQUOTE(JSON_EXTRACT(r.payload,'$.isClosed'))) IN ('true','1','yes','y') THEN 1
      ELSE 0
    END AS is_closed,

    JSON_UNQUOTE(JSON_EXTRACT(r.payload,'$.dateOfClosed')) AS date_of_closed,
    JSON_UNQUOTE(JSON_EXTRACT(r.payload,'$.summerOpenTime')) AS summer_open_time,
    JSON_UNQUOTE(JSON_EXTRACT(r.payload,'$.winterOpenTime')) AS winter_open_time,
    JSON_UNQUOTE(JSON_EXTRACT(r.payload,'$.faxNumber')) AS fax_number,
    JSON_UNQUOTE(JSON_EXTRACT(r.payload,'$.phone')) AS phone,
    JSON_UNQUOTE(JSON_EXTRACT(r.payload,'$.location')) AS location_uri,
    JSON_EXTRACT(r.payload,'$.homepage') AS homepage_json,
    JSON_UNQUOTE(JSON_EXTRACT(r.payload,'$.subject')) AS subject,

    r.payload AS raw_payload,
    r.raw_id AS last_raw_id,
    r.payload_hash AS last_payload_hash
  FROM raw_node r
  WHERE JSON_UNQUOTE(JSON_EXTRACT(r.payload,'$."@type"')) = 'nlon:Library'
    AND r.entity_kind IN ('AGENT','LIBRARY')
) x
ON DUPLICATE KEY UPDATE
                       identifier=VALUES(identifier),
                       label=VALUES(label),
                       keyword=VALUES(keyword),
                       library_type=VALUES(library_type),
                       opening_year=VALUES(opening_year),
                       date_of_opening=VALUES(date_of_opening),
                       is_closed=VALUES(is_closed),
                       date_of_closed=VALUES(date_of_closed),
                       summer_open_time=VALUES(summer_open_time),
                       winter_open_time=VALUES(winter_open_time),
                       fax_number=VALUES(fax_number),
                       phone=VALUES(phone),
                       location_uri=VALUES(location_uri),
                       homepage_json=VALUES(homepage_json),
                       subject=VALUES(subject),
                       raw_payload=VALUES(raw_payload),
                       last_raw_id=VALUES(last_raw_id),
                       last_payload_hash=VALUES(last_payload_hash),
                       updated_at=NOW();


-- ------------------------------------------------------------
-- 5) Material (BOOK / OFFLINE, etc) : raw_node.payload
-- ------------------------------------------------------------
INSERT IGNORE INTO material (
  material_id,
  material_kind,
  title,
  subtitle,
  label,
  description,
  publisher,
  publication_place,
  issued_year,
  date_published,
  language,
  raw_payload,
  last_raw_id,
  last_payload_hash,
  created_at,
  updated_at
)
SELECT
  r.node_id AS material_id,

  CASE
    WHEN JSON_CONTAINS(
      JSON_EXTRACT(r.payload, '$."@type"'),
      JSON_QUOTE('bibo:Book')
         ) THEN 'BOOK'
    ELSE 'OFFLINE'
    END AS material_kind,

  JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.title')) AS title,
  JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.remainderOfTitle')) AS subtitle,
  JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.label')) AS label,
  JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.description')) AS description,

  JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.publisher')) AS publisher,
  JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.publicationPlace')) AS publication_place,

  CAST(JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.issuedYear')) AS UNSIGNED) AS issued_year,
  CASE
    WHEN JSON_EXTRACT(r.payload, '$.datePublished') IS NULL THEN NULL
    WHEN SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.datePublished')), '^^', 1)
      REGEXP '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}$'
    THEN STR_TO_DATE(
      SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.datePublished')), '^^', 1),
      '%Y-%m-%dT%H:%i:%s'
         )
    ELSE NULL
    END AS date_published,

  JSON_UNQUOTE(JSON_EXTRACT(r.payload, '$.language')) AS language,

  r.payload AS raw_payload,
  r.raw_id,
  r.payload_hash,
  NOW(),
  NOW()
FROM raw_node r
WHERE r.entity_kind = 'MATERIAL'
  AND r.node_id LIKE 'nlk:%'
ON DUPLICATE KEY UPDATE
                   material_kind = VALUES(material_kind),
                   title = VALUES(title),
                   subtitle = VALUES(subtitle),
                   label = VALUES(label),
                   description = VALUES(description),
                   publisher = VALUES(publisher),
                   publication_place = VALUES(publication_place),
                   issued_year = VALUES(issued_year),
                   date_published = VALUES(date_published),
                   language = VALUES(language),
                   raw_payload = VALUES(raw_payload),
                   last_raw_id = VALUES(last_raw_id),
                   last_payload_hash = VALUES(last_payload_hash),
                   updated_at = NOW();

-- It’s cleaner to compute material_kind and date_published in the SELECT, so here’s a redefined version as recommended:
-- (If the INSERT above already exists, use only this “recommended version” below and remove the block above.)

-- -------- Recommended version (includes material_kind/date_published computation) --------
-- INSERT INTO material (...)
-- SELECT
--   jt.material_id,
--   CASE
--     WHEN jt.type_arr IS NOT NULL AND JSON_SEARCH(jt.type_arr,'one','bibo:Book') IS NOT NULL THEN 'BOOK'
--     ELSE 'OFFLINE'
--   END AS material_kind,
--   ...
--   CASE
--     WHEN jt.date_published_raw IS NULL THEN NULL
--     ELSE STR_TO_DATE(SUBSTRING_INDEX(jt.date_published_raw,'^^',1), '%Y-%m-%dT%H:%i:%s')
--   END AS date_published,
--   ...
-- FROM ...
-- ON DUPLICATE KEY UPDATE ...


-- ------------------------------------------------------------
-- 6) Material identifiers (isbn / itemNumberOfNLK / localHolding 등)
-- ------------------------------------------------------------
-- 6-1) ISBN
INSERT IGNORE INTO material_identifier (material_id, scheme, value)
SELECT
  m.material_id,
  'ISBN' AS scheme,
  JSON_UNQUOTE(JSON_EXTRACT(m.raw_payload, '$.isbn')) AS value
FROM material m
WHERE JSON_EXTRACT(m.raw_payload, '$.isbn') IS NOT NULL
  AND JSON_UNQUOTE(JSON_EXTRACT(m.raw_payload, '$.isbn')) <> '';

-- 6-2) itemNumberOfNLK
INSERT IGNORE INTO material_identifier (material_id, scheme, value)
SELECT
  m.material_id,
  'NLK_ITEMNO' AS scheme,
  JSON_UNQUOTE(JSON_EXTRACT(m.raw_payload, '$.itemNumberOfNLK')) AS value
FROM material m
WHERE JSON_EXTRACT(m.raw_payload, '$.itemNumberOfNLK') IS NOT NULL
  AND JSON_UNQUOTE(JSON_EXTRACT(m.raw_payload, '$.itemNumberOfNLK')) <> '';

-- 6-3) localHolding
INSERT IGNORE INTO material_identifier (material_id, scheme, value)
SELECT
  m.material_id,
  'NLK_LOCALHOLDING' AS scheme,
  jt.val AS value
FROM material m
  JOIN JSON_TABLE(
  CASE
  WHEN JSON_TYPE(JSON_EXTRACT(m.raw_payload, '$.localHolding'))='ARRAY'
  THEN JSON_EXTRACT(m.raw_payload, '$.localHolding')
  WHEN JSON_TYPE(JSON_EXTRACT(m.raw_payload, '$.localHolding')) IN ('STRING','OBJECT')
  THEN JSON_ARRAY(JSON_EXTRACT(m.raw_payload, '$.localHolding'))
  ELSE JSON_ARRAY()
  END,
  '$[*]' COLUMNS (val VARCHAR(128) PATH '$')
  ) jt
WHERE jt.val IS NOT NULL
  AND jt.val <> '';


-- ------------------------------------------------------------
-- 7) Material -> Agent link (creator / dcterms:creator)
-- ------------------------------------------------------------
INSERT IGNORE INTO material_agent (material_id, agent_id, role)
SELECT
  m.material_id,
  CASE
    WHEN JSON_TYPE(j.elem) = 'OBJECT' THEN JSON_UNQUOTE(JSON_EXTRACT(j.elem, '$."@id"'))
    WHEN JSON_TYPE(j.elem) = 'STRING' THEN JSON_UNQUOTE(j.elem)
    ELSE NULL
    END AS agent_id,
  'CREATOR' AS role
FROM material m
       JOIN JSON_TABLE(
  JSON_MERGE_PRESERVE(
    CASE
      WHEN JSON_TYPE(JSON_EXTRACT(m.raw_payload, '$.creator'))='ARRAY'
        THEN JSON_EXTRACT(m.raw_payload, '$.creator')
      WHEN JSON_TYPE(JSON_EXTRACT(m.raw_payload, '$.creator')) IN ('OBJECT','STRING')
        THEN JSON_ARRAY(JSON_EXTRACT(m.raw_payload, '$.creator'))
      ELSE JSON_ARRAY()
      END,
    CASE
      WHEN JSON_TYPE(JSON_EXTRACT(m.raw_payload, '$."dcterms:creator"'))='ARRAY'
        THEN JSON_EXTRACT(m.raw_payload, '$."dcterms:creator"')
      WHEN JSON_TYPE(JSON_EXTRACT(m.raw_payload, '$."dcterms:creator"')) IN ('OBJECT','STRING')
        THEN JSON_ARRAY(JSON_EXTRACT(m.raw_payload, '$."dcterms:creator"'))
      ELSE JSON_ARRAY()
      END
  ),
  '$[*]' COLUMNS (elem JSON PATH '$')
            ) j
WHERE (
        (JSON_TYPE(j.elem)='OBJECT' AND JSON_UNQUOTE(JSON_EXTRACT(j.elem, '$."@id"')) LIKE 'nlk:%')
          OR (JSON_TYPE(j.elem)='STRING' AND JSON_UNQUOTE(j.elem) LIKE 'nlk:%')
        );


-- ------------------------------------------------------------
-- 8) Material -> Concept link (subject)
-- ------------------------------------------------------------
INSERT IGNORE INTO material_concept (material_id, concept_id, role)
SELECT
  m.material_id,
  CASE
    WHEN JSON_TYPE(j.elem) = 'OBJECT' THEN JSON_UNQUOTE(JSON_EXTRACT(j.elem, '$."@id"'))
    WHEN JSON_TYPE(j.elem) = 'STRING' THEN JSON_UNQUOTE(j.elem)
    ELSE NULL
    END AS concept_id,
  'SUBJECT' AS role
FROM material m
       JOIN JSON_TABLE(
  CASE
    WHEN JSON_TYPE(JSON_EXTRACT(m.raw_payload, '$.subject'))='ARRAY'
      THEN JSON_EXTRACT(m.raw_payload, '$.subject')
    WHEN JSON_TYPE(JSON_EXTRACT(m.raw_payload, '$.subject')) IN ('OBJECT','STRING')
      THEN JSON_ARRAY(JSON_EXTRACT(m.raw_payload, '$.subject'))
    ELSE JSON_ARRAY()
    END,
  '$[*]' COLUMNS (elem JSON PATH '$')
            ) j
WHERE (
        (JSON_TYPE(j.elem)='OBJECT' AND JSON_UNQUOTE(JSON_EXTRACT(j.elem, '$."@id"')) LIKE 'nlk:%')
          OR (JSON_TYPE(j.elem)='STRING' AND JSON_UNQUOTE(j.elem) LIKE 'nlk:%')
        );


/* ============================================================
    Done.
    - Skip sameAs
    - agent_alt_label / agent_language are optional
    - Recommend consolidating material_kind/date_published into the recommended version above
   ============================================================ */
