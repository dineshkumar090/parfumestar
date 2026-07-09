-- Add missing columns to chatbot_configs (run if auto-migration on startup is disabled)
-- Safe to re-run only if columns don't exist yet.

ALTER TABLE `chatbot_configs` ADD COLUMN `button_text` VARCHAR(200) NULL DEFAULT 'Ask me anything!';
ALTER TABLE `chatbot_configs` ADD COLUMN `cart_icon` VARCHAR(50) NULL DEFAULT 'mdi:cart';
ALTER TABLE `chatbot_configs` ADD COLUMN `cart_enabled` TINYINT(1) NULL DEFAULT 1;
ALTER TABLE `chatbot_configs` ADD COLUMN `header_icon` VARCHAR(50) NULL DEFAULT '🤖';
ALTER TABLE `chatbot_configs` ADD COLUMN `system_prompts` JSON NULL;
ALTER TABLE `chatbot_configs` ADD COLUMN `tool_decision_prompt` TEXT NULL;
ALTER TABLE `chatbot_configs` ADD COLUMN `answer_generation_prompt` TEXT NULL;
ALTER TABLE `chatbot_configs` ADD COLUMN `product_description_prompt` TEXT NULL;
ALTER TABLE `chatbot_configs` ADD COLUMN `embedding_prompt_template` TEXT NULL;
ALTER TABLE `chatbot_configs` ADD COLUMN `comparison_prompt` TEXT NULL;
ALTER TABLE `chatbot_configs` ADD COLUMN `suggestion_prompt` TEXT NULL;
ALTER TABLE `chatbot_configs` ADD COLUMN `order_status_prompt` TEXT NULL;
ALTER TABLE `chatbot_configs` ADD COLUMN `smalltalk_responses` JSON NULL;
ALTER TABLE `chatbot_configs` ADD COLUMN `greeting_templates` JSON NULL;
ALTER TABLE `chatbot_configs` ADD COLUMN `product_count_templates` JSON NULL;
ALTER TABLE `chatbot_configs` ADD COLUMN `enable_smalltalk` TINYINT(1) NULL DEFAULT 1;
ALTER TABLE `chatbot_configs` ADD COLUMN `enable_product_comparison` TINYINT(1) NULL DEFAULT 1;
ALTER TABLE `chatbot_configs` ADD COLUMN `enable_price_filtering` TINYINT(1) NULL DEFAULT 1;
ALTER TABLE `chatbot_configs` ADD COLUMN `enable_variant_detection` TINYINT(1) NULL DEFAULT 1;
ALTER TABLE `chatbot_configs` ADD COLUMN `enable_followup_detection` TINYINT(1) NULL DEFAULT 1;
ALTER TABLE `chatbot_configs` ADD COLUMN `show_evaluation_button` TINYINT(1) NULL DEFAULT 0;
