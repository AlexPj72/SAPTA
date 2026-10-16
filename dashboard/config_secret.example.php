<?php
// COPIARE come config_secret.php SOLO sul server Aruba (accanto a config.php) e compilare i due valori.
// config_secret.php NON va mai messo su GitHub (e' nel .gitignore).
// Chiave: la "secret" (sb_secret_...) o la "service_role" di Supabase (Project Settings > API Keys). Non e' l'ID del progetto.
define('SUPABASE_SERVICE_KEY', 'INCOLLA_QUI_LA_CHIAVE_SECRET');
// Password per entrare in portafoglio.php (senza password la pagina resta chiusa).
define('PORTAFOGLIO_PASSWORD', 'SCEGLI_UNA_PASSWORD');
