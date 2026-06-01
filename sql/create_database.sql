-- Replace CHANGE_THIS_DB_PASSWORD with a strong password and update server_config.ini to match.
CREATE DATABASE IF NOT EXISTS sa_us_erp CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'sa_us_user'@'localhost' IDENTIFIED BY 'CHANGE_THIS_DB_PASSWORD';
GRANT ALL PRIVILEGES ON sa_us_erp.* TO 'sa_us_user'@'localhost';
FLUSH PRIVILEGES;
