DELIMITER $$

CREATE PROCEDURE add_audit_columns_if_missing()
BEGIN
    DECLARE done INT DEFAULT 0;
    DECLARE table_name_value VARCHAR(128);
    DECLARE has_created_at INT DEFAULT 0;
    DECLARE has_updated_at INT DEFAULT 0;
    DECLARE has_deleted_at INT DEFAULT 0;
    DECLARE sep VARCHAR(3);
    DECLARE alter_sql TEXT;

    DECLARE table_cursor CURSOR FOR
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_type = 'BASE TABLE'
          AND table_name <> 'flyway_schema_history'
        ORDER BY table_name;

    DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = 1;

    OPEN table_cursor;

    table_loop: LOOP
        FETCH table_cursor INTO table_name_value;
        IF done = 1 THEN
            LEAVE table_loop;
        END IF;

        SELECT COUNT(*)
        INTO has_created_at
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = table_name_value
          AND column_name = 'created_at';

        SELECT COUNT(*)
        INTO has_updated_at
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = table_name_value
          AND column_name = 'updated_at';

        SELECT COUNT(*)
        INTO has_deleted_at
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = table_name_value
          AND column_name = 'deleted_at';

        IF has_created_at = 0 OR has_updated_at = 0 OR has_deleted_at = 0 THEN
            SET alter_sql = CONCAT('ALTER TABLE `', REPLACE(table_name_value, '`', '``'), '`');
            SET sep = ' ';

            IF has_created_at = 0 THEN
                SET alter_sql = CONCAT(alter_sql, sep,
                    'ADD COLUMN `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP');
                SET sep = ', ';
            END IF;

            IF has_updated_at = 0 THEN
                SET alter_sql = CONCAT(alter_sql, sep,
                    'ADD COLUMN `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP');
                SET sep = ', ';
            END IF;

            IF has_deleted_at = 0 THEN
                SET alter_sql = CONCAT(alter_sql, sep,
                    'ADD COLUMN `deleted_at` DATETIME NULL DEFAULT NULL');
            END IF;

            SET @migration_sql = alter_sql;
            PREPARE stmt FROM @migration_sql;
            EXECUTE stmt;
            DEALLOCATE PREPARE stmt;
        END IF;
    END LOOP;

    CLOSE table_cursor;
END$$

DELIMITER ;

CALL add_audit_columns_if_missing();
DROP PROCEDURE add_audit_columns_if_missing;
