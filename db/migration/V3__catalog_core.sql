CREATE TABLE agent (
                     agent_id               VARCHAR(64)                        NOT NULL PRIMARY KEY,
                     agent_type             VARCHAR(16)                        NOT NULL, -- PERSON | ORGANIZATION
                     pref_label             VARCHAR(512)                       NULL,
                     label                  VARCHAR(512)                       NULL,
                     name                   VARCHAR(512)                       NULL,
                     isni                   VARCHAR(32)                        NULL,
                     url                    VARCHAR(1024)                      NULL,
                     location               VARCHAR(255)                       NULL,
                     gender                 VARCHAR(32)                        NULL,
                     birth_year             INT                                NULL,
                     death_year             INT                                NULL,
                     corporate_name         VARCHAR(512)                       NULL,
                     job_title              VARCHAR(255)                       NULL,
                     date_of_establishment  DATE                               NULL,
                     date_published         DATETIME                           NULL,
                     modified_at            DATETIME                           NULL,
                     field_of_activity_json JSON                               NULL,
                     source_json            JSON                               NULL,
                     raw_payload            JSON                               NOT NULL,
                     last_raw_id            BIGINT                             NULL,
                     last_payload_hash      CHAR(64)                           NULL,
                     created_at             DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                     updated_at             DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_agent_type       ON agent (agent_type);
CREATE INDEX idx_agent_pref_label ON agent (pref_label);
CREATE INDEX idx_agent_label      ON agent (label);
CREATE INDEX idx_agent_isni       ON agent (isni);

CREATE TABLE concept (
                       concept_id         VARCHAR(64)                        NOT NULL PRIMARY KEY,
                       pref_label         VARCHAR(512)                       NULL,
                       label              VARCHAR(512)                       NULL,
                       broader_concept_id VARCHAR(64)                        NULL,
                       scheme_id          VARCHAR(64)                        NULL,
                       raw_payload        JSON                               NOT NULL,
                       last_raw_id        BIGINT                             NULL,
                       last_payload_hash  CHAR(64)                           NULL,
                       created_at         DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                       updated_at         DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_concept_broader    ON concept (broader_concept_id);
CREATE INDEX idx_concept_scheme     ON concept (scheme_id);
CREATE INDEX idx_concept_pref_label ON concept (pref_label);
CREATE INDEX idx_concept_label      ON concept (label);

CREATE TABLE library (
                       library_id        VARCHAR(64)                        NOT NULL PRIMARY KEY, -- nllib:...
                       identifier        VARCHAR(64)                        NULL,                  -- KR-xxxxx
                       label             VARCHAR(512)                       NULL,
                       keyword           VARCHAR(255)                       NULL,
                       library_type      VARCHAR(255)                       NULL,
                       opening_year      INT                                NULL,
                       date_of_opening   DATE                               NULL,
                       is_closed         TINYINT(1)                         NULL,
                       date_of_closed    VARCHAR(255)                       NULL,
                       summer_open_time  VARCHAR(64)                        NULL,
                       winter_open_time  VARCHAR(64)                        NULL,
                       fax_number        VARCHAR(64)                        NULL,
                       phone             VARCHAR(64)                        NULL,
                       location_uri      VARCHAR(1024)                      NULL,
                       homepage_json     JSON                               NULL,
                       subject           VARCHAR(255)                       NULL,
                       raw_payload       JSON                               NOT NULL,
                       last_raw_id       BIGINT                             NULL,
                       last_payload_hash CHAR(64)                           NULL,
                       created_at        DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                       updated_at        DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_library_identifier ON library (identifier);
CREATE INDEX idx_library_label      ON library (label);

CREATE TABLE material (
                        material_id       VARCHAR(64)                        NOT NULL PRIMARY KEY, -- nlk:CMO..., nlk:CDM...
                        material_kind     VARCHAR(32)                        NOT NULL,             -- BOOK | OFFLINE | ...
                        title             VARCHAR(2048)                      NULL,
                        subtitle          VARCHAR(2048)                      NULL,
                        label             VARCHAR(2048)                      NULL,
                        description       LONGTEXT                           NULL,
                        publisher         VARCHAR(1024)                      NULL,
                        publication_place VARCHAR(255)                       NULL,
                        issued_year       INT                                NULL,
                        date_published    DATETIME                           NULL,
                        language          VARCHAR(512)                       NULL,
                        raw_payload       JSON                               NOT NULL,
                        last_raw_id       BIGINT                             NULL,
                        last_payload_hash CHAR(64)                           NULL,
                        created_at        DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                        updated_at        DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_material_kind         ON material (material_kind);
CREATE INDEX idx_material_issued_year  ON material (issued_year);
CREATE INDEX idx_material_title_prefix ON material (title(255));
CREATE INDEX idx_material_publisher    ON material (publisher(191));

CREATE TABLE agent_alt_label (
                               agent_id  VARCHAR(64)  NOT NULL,
                               alt_label VARCHAR(512) NOT NULL,
                               PRIMARY KEY (agent_id, alt_label)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_alt_label ON agent_alt_label (alt_label);

CREATE TABLE agent_language (
                              agent_id  VARCHAR(64) NOT NULL,
                              language  VARCHAR(64) NOT NULL,
                              PRIMARY KEY (agent_id, language)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_language ON agent_language (language);

CREATE TABLE material_identifier (
                                   material_id VARCHAR(64)  NOT NULL,
                                   scheme      VARCHAR(32)  NOT NULL,
                                   value       VARCHAR(128) NOT NULL,
                                   PRIMARY KEY (material_id, scheme, value)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_identifier_lookup ON material_identifier (scheme, value);
CREATE INDEX idx_identifier_value  ON material_identifier (value);

CREATE TABLE material_agent (
                              material_id VARCHAR(64) NOT NULL,
                              agent_id    VARCHAR(64) NOT NULL,
                              role        VARCHAR(32) NOT NULL,
                              PRIMARY KEY (material_id, agent_id, role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_ma_agent ON material_agent (agent_id);
CREATE INDEX idx_ma_role  ON material_agent (role);

CREATE TABLE material_concept (
                                material_id VARCHAR(64) NOT NULL,
                                concept_id  VARCHAR(64) NOT NULL,
                                role        VARCHAR(32) NOT NULL,
                                PRIMARY KEY (material_id, concept_id, role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_mc_concept ON material_concept (concept_id);
CREATE INDEX idx_mc_role    ON material_concept (role);

