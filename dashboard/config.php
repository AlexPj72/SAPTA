<?php
// Configurazione Supabase — progetto "sapta"
define('SUPABASE_URL', 'https://wpgozxddhlmzgymvpacq.supabase.co');
define('SUPABASE_ANON_KEY', 'sb_publishable_oVcCx692_mxEzJTQMN8khA_TGMnPnMA');

// Funzione helper per chiamate GET all'API REST di Supabase
function supabase_query($table, $params = []) {
    $url = SUPABASE_URL . '/rest/v1/' . $table;

    if (!empty($params)) {
        $url .= '?' . http_build_query($params);
    }

    $ch = curl_init($url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_HTTPHEADER, [
        'apikey: ' . SUPABASE_ANON_KEY,
        'Authorization: Bearer ' . SUPABASE_ANON_KEY
    ]);

    $response = curl_exec($ch);
    curl_close($ch);

    $data = json_decode($response, true);
    return is_array($data) ? $data : [];
}
?>
