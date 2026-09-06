-- 2026-09-06: additive parent delegation, MySQL 8.0.16+.
-- Run against the explicitly selected application database. No user or chat data is modified.

CREATE TABLE IF NOT EXISTS parent_relationship (
        parent_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
        child_id BIGINT UNSIGNED NULL,
        status VARCHAR(16) NOT NULL DEFAULT 'pending',
        expires_at DATETIME(6) NULL,
        consent_version VARCHAR(64) NOT NULL DEFAULT 'parent-consent@1',
        invite_hash CHAR(64) NULL,
        invite_expires_at DATETIME(6) NULL,
        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        UNIQUE KEY uk_parent_invite (invite_hash),
        KEY idx_parent_child (child_id, status),
        CONSTRAINT fk_parent_relation_parent FOREIGN KEY (parent_id) REFERENCES users(id),
        CONSTRAINT fk_parent_relation_child FOREIGN KEY (child_id) REFERENCES users(id),
        CONSTRAINT ck_parent_relation_status CHECK (status IN ('pending', 'granted', 'revoked')),
        CONSTRAINT ck_parent_relation_distinct CHECK (child_id IS NULL OR child_id <> parent_id),
        CONSTRAINT ck_parent_relation_grant CHECK (status <> 'granted' OR (child_id IS NOT NULL AND expires_at IS NOT NULL))
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS parent_preferences (
        user_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
        message_notifications TINYINT NOT NULL DEFAULT 1,
        allow_parent_photo TINYINT NOT NULL DEFAULT 0,
        CONSTRAINT fk_parent_preferences_user FOREIGN KEY (user_id) REFERENCES users(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS parent_action_event (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        actor_id BIGINT UNSIGNED NOT NULL,
        parent_id BIGINT UNSIGNED NOT NULL,
        child_id BIGINT UNSIGNED NULL,
        action VARCHAR(64) NOT NULL,
        target_id BIGINT UNSIGNED NULL,
        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        KEY idx_parent_event (parent_id, created_at),
        KEY idx_child_event (child_id, created_at),
        CONSTRAINT fk_parent_event_actor FOREIGN KEY (actor_id) REFERENCES users(id),
        CONSTRAINT fk_parent_event_parent FOREIGN KEY (parent_id) REFERENCES users(id),
        CONSTRAINT fk_parent_event_child FOREIGN KEY (child_id) REFERENCES users(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
