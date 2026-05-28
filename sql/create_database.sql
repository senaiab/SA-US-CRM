-- SA-US ERP database bootstrap script
-- Replace CHANGE_ME_WITH_STRONG_PASSWORD before running this script.

CREATE DATABASE IF NOT EXISTS sa_us_erp CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'sa_us_user'@'localhost' IDENTIFIED BY 'CHANGE_ME_WITH_STRONG_PASSWORD';
ALTER USER 'sa_us_user'@'localhost' IDENTIFIED BY 'CHANGE_ME_WITH_STRONG_PASSWORD';
GRANT ALL PRIVILEGES ON sa_us_erp.* TO 'sa_us_user'@'localhost';
FLUSH PRIVILEGES;
