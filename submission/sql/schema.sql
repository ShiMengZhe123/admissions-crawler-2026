CREATE DATABASE IF NOT EXISTS admissions
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_bin;

USE admissions;

CREATE TABLE IF NOT EXISTS admission_plan_v2 (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    admission_year SMALLINT UNSIGNED NOT NULL,
    school VARCHAR(40) NOT NULL,
    province VARCHAR(40) NOT NULL,
    college_name VARCHAR(200) NULL,
    major_code VARCHAR(32) NULL,
    major_name VARCHAR(240) NOT NULL,
    subject_type VARCHAR(80) NULL,
    batch_name VARCHAR(120) NULL,
    plan_type VARCHAR(120) NULL,
    selection_subject TEXT NULL,
    fee_text VARCHAR(160) NULL,
    planned_count INT UNSIGNED NOT NULL,
    source_url VARCHAR(1000) NOT NULL,
    source_image VARCHAR(500) NULL,
    source_row INT NULL,
    source_box TEXT NULL,
    extraction_method VARCHAR(16) NOT NULL,
    review_status VARCHAR(32) NOT NULL DEFAULT '未验证',
    review_reason TEXT NULL,
    record_hash CHAR(64) NOT NULL,
    fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uniq_record_hash (record_hash),
    KEY idx_school_year_province (school, admission_year, province),
    KEY idx_review_status (review_status),
    CONSTRAINT chk_plan_count CHECK (planned_count > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
