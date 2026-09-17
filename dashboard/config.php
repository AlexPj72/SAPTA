<?php
// Configurazione Supabase — progetto "sapta"
define('SUPABASE_URL', 'https://wpgozxddhlmzgymvpacq.supabase.co');
define('SUPABASE_ANON_KEY', 'sb_publishable_oVcCx692_mxEzJTQMN8khA_TGMnPnMA');

// [NUOVO 17/09] Stessa chiave Gemini già usata da Modulo I (GitHub Actions
// secret GEMINI_API_KEY) - usala qui per la Chat AI. Se lasci vuoto, la
// pagina chat.php mostra un avviso invece di rompersi.
define('GEMINI_API_KEY', '');

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

// POST/PATCH helper (usato da decisions.php e capital.php) - accorpa il
// codice curl duplicato che c'era in entrambi i file.
function supabase_write($table, $payload, $method = 'POST', $filter = '') {
    $url = SUPABASE_URL . '/rest/v1/' . $table . $filter;
    $ch = curl_init($url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    if ($method === 'PATCH') {
        curl_setopt($ch, CURLOPT_CUSTOMREQUEST, 'PATCH');
    } else {
        curl_setopt($ch, CURLOPT_POST, true);
    }
    curl_setopt($ch, CURLOPT_HTTPHEADER, [
        'apikey: ' . SUPABASE_ANON_KEY,
        'Authorization: Bearer ' . SUPABASE_ANON_KEY,
        'Content-Type: application/json',
        'Prefer: return=minimal'
    ]);
    curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($payload));
    curl_exec($ch);
    $http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    return $http_code;
}
