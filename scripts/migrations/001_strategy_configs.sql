-- Migration: Strategy Configuration Management Tables
-- Description: Creates tables for storing strategy configurations, per-symbol overrides, and audit trails
-- Date: 2025-10-17

-- ============================================================================
-- Global Strategy Configurations
-- ============================================================================
CREATE TABLE IF NOT EXISTS strategy_configs_global (
    id VARCHAR(36) PRIMARY KEY DEFAULT (UUID()),
    strategy_id VARCHAR(100) NOT NULL,
    parameters JSON NOT NULL COMMENT 'Strategy parameter key-value pairs',
    version INT NOT NULL DEFAULT 1 COMMENT 'Configuration version, incremented on updates',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'When config was first created',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'When config was last updated',
    created_by VARCHAR(100) COMMENT 'Who/what created this config (e.g., llm_agent_v1)',
    metadata JSON COMMENT 'Additional metadata (notes, performance metrics, etc.)',
    UNIQUE KEY unique_strategy (strategy_id),
    INDEX idx_updated_at (updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci 
COMMENT='Global strategy configurations applied to all symbols';

-- ============================================================================
-- Symbol-Specific Strategy Configurations (Overrides)
-- ============================================================================
CREATE TABLE IF NOT EXISTS strategy_configs_symbol (
    id VARCHAR(36) PRIMARY KEY DEFAULT (UUID()),
    strategy_id VARCHAR(100) NOT NULL,
    symbol VARCHAR(20) NOT NULL COMMENT 'Trading symbol (e.g., BTCUSDT)',
    parameters JSON NOT NULL COMMENT 'Symbol-specific parameter overrides',
    version INT NOT NULL DEFAULT 1 COMMENT 'Configuration version, incremented on updates',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'When config was first created',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'When config was last updated',
    created_by VARCHAR(100) COMMENT 'Who/what created this config',
    metadata JSON COMMENT 'Additional metadata',
    UNIQUE KEY unique_strategy_symbol (strategy_id, symbol),
    INDEX idx_strategy (strategy_id),
    INDEX idx_symbol (symbol),
    INDEX idx_updated_at (updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci 
COMMENT='Symbol-specific strategy configurations that override global configs';

-- ============================================================================
-- Configuration Audit Trail
-- ============================================================================
CREATE TABLE IF NOT EXISTS strategy_config_audit (
    id VARCHAR(36) PRIMARY KEY DEFAULT (UUID()),
    config_id VARCHAR(36) COMMENT 'Reference to the config that was changed',
    strategy_id VARCHAR(100) NOT NULL,
    symbol VARCHAR(20) COMMENT 'NULL for global configs, symbol name for symbol-specific',
    action ENUM('CREATE', 'UPDATE', 'DELETE') NOT NULL COMMENT 'Type of change',
    old_parameters JSON COMMENT 'Previous parameter values (NULL for CREATE)',
    new_parameters JSON COMMENT 'New parameter values (NULL for DELETE)',
    changed_by VARCHAR(100) NOT NULL COMMENT 'Who/what made the change',
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'When the change occurred',
    reason TEXT COMMENT 'Optional explanation for the change',
    INDEX idx_strategy_symbol (strategy_id, symbol),
    INDEX idx_changed_at (changed_at),
    INDEX idx_changed_by (changed_by),
    INDEX idx_action (action)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci 
COMMENT='Audit trail for all configuration changes with full history';

-- ============================================================================
-- Verification Queries
-- ============================================================================
-- Run these after migration to verify table creation:
-- 
-- SHOW TABLES LIKE 'strategy_config%';
-- DESCRIBE strategy_configs_global;
-- DESCRIBE strategy_configs_symbol;
-- DESCRIBE strategy_config_audit;

