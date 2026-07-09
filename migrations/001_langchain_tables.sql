-- Run this on your MySQL database if startup create_all fails or you prefer manual DDL.
-- Database: modernalchemy_db (or your MYSQL_DB from .env)
-- Port: 3066

-- Unified products (international + Shopify)
CREATE TABLE IF NOT EXISTS `main_database` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `source_type` VARCHAR(32) NOT NULL,
  `source_id` VARCHAR(64) NOT NULL,
  `shop_url` VARCHAR(255) DEFAULT NULL,
  `title` VARCHAR(500) DEFAULT NULL,
  `description` TEXT,
  `handle` VARCHAR(255) DEFAULT NULL,
  `featured_image` TEXT,
  `brand` VARCHAR(255) DEFAULT NULL,
  `product_type` VARCHAR(100) DEFAULT NULL,
  `gender` VARCHAR(50) DEFAULT NULL,
  `year` INT DEFAULT NULL,
  `status` VARCHAR(50) DEFAULT 'active',
  `price` FLOAT DEFAULT NULL,
  `vendor` VARCHAR(255) DEFAULT NULL,
  `olfactive` VARCHAR(500) DEFAULT NULL,
  `top_note` VARCHAR(500) DEFAULT NULL,
  `heart_note` VARCHAR(500) DEFAULT NULL,
  `base_note` VARCHAR(500) DEFAULT NULL,
  `ingredients` TEXT,
  `shopify_gid` VARCHAR(100) DEFAULT NULL,
  `metafields` JSON DEFAULT NULL,
  `variants` JSON DEFAULT NULL,
  `tags` VARCHAR(500) DEFAULT NULL,
  `collections` JSON DEFAULT NULL,
  `linked_shopify_products` JSON DEFAULT NULL,
  `custom_data` JSON DEFAULT NULL,
  `pinecone_id` VARCHAR(100) DEFAULT NULL,
  `embedding_synced_at` DATETIME DEFAULT NULL,
  `is_enabled` INT DEFAULT 1,
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_main_db_source` (`source_type`, `source_id`),
  KEY `ix_main_database_source_type` (`source_type`),
  KEY `ix_main_database_shop_url` (`shop_url`),
  KEY `ix_main_database_pinecone_id` (`pinecone_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- LangChain intent logging per chat message
CREATE TABLE IF NOT EXISTS `chat_intent_logs` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `message_id` INT DEFAULT NULL,
  `thread_id` INT DEFAULT NULL,
  `shop` VARCHAR(255) NOT NULL,
  `intent` VARCHAR(80) NOT NULL,
  `confidence` FLOAT DEFAULT 0,
  `is_international_reference` INT DEFAULT 0,
  `is_own_product` INT DEFAULT 0,
  `product_name` VARCHAR(500) DEFAULT NULL,
  `pipeline_path` VARCHAR(100) DEFAULT NULL,
  `metadata_json` TEXT,
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_chat_intent_logs_message_id` (`message_id`),
  KEY `ix_chat_intent_logs_thread_id` (`thread_id`),
  KEY `ix_chat_intent_logs_shop` (`shop`),
  KEY `ix_chat_intent_logs_intent` (`intent`),
  CONSTRAINT `fk_intent_message` FOREIGN KEY (`message_id`) REFERENCES `chat_messages` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_intent_thread` FOREIGN KEY (`thread_id`) REFERENCES `chat_threads` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
