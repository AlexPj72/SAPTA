<?php
// COPIARE come config_secret.php SOLO sul server Aruba (accanto a config.php) e inserire la chiave.
// config_secret.php NON va mai messo su GitHub (e' nel .gitignore).
// La chiave e' la "service_role" di Supabase (Project Settings > API Keys): serve solo alla pagina portafoglio.php.
define('SUPABASE_SERVICE_KEY', 'INCOLLA_QUI_LA_CHIAVE_SERVICE_ROLE');
