-- Normalized fragrance notes for SQL matching (international ↔ Shopify)
CREATE TABLE IF NOT EXISTS `perfume_notes` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `unified_product_id` INT NOT NULL,
  `source_type` VARCHAR(32) NOT NULL,
  `note_type` VARCHAR(32) NOT NULL,
  `note_name` VARCHAR(255) NOT NULL,
  `note_raw` VARCHAR(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_perfume_notes_unified_product_id` (`unified_product_id`),
  KEY `ix_perfume_notes_source_type` (`source_type`),
  KEY `ix_perfume_notes_note_type` (`note_type`),
  KEY `ix_perfume_notes_note_name` (`note_name`),
  KEY `ix_perfume_notes_match` (`source_type`, `note_name`),
  KEY `ix_perfume_notes_product_type` (`unified_product_id`, `note_type`),
  CONSTRAINT `fk_perfume_notes_main_db` FOREIGN KEY (`unified_product_id`)
    REFERENCES `main_database` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
