<?php
// Livelli di uscita automatici per acquisti senza segnale SAPTA (manuali, utente o ChatGPT).
// Stesse regole dei segnali (modulo_b_analysis.py): stop = ingresso - 1,5 x ATR(14), target = ingresso + 3 x ATR(14) (rapporto 1:2).
// L'ATR(14) (media di Wilder) usa le barre giornaliere precedenti al giorno dell'acquisto: il risultato e' sempre lo stesso per la stessa posizione.
function pf_atr14($ticker, $until_iso) {
    $rows = supabase_query('prezzi', ['select' => 'timestamp,high,low,close', 'ticker' => 'eq.' . $ticker, 'interval' => 'eq.1d',
        'timestamp' => 'lt.' . gmdate('Y-m-d\T00:00:00\Z', strtotime((string)$until_iso)), 'order' => 'timestamp.desc', 'limit' => 60]);
    if (!is_array($rows) || count($rows) < 20) return null;
    $rows = array_reverse($rows);
    $tr = [];
    for ($i = 1; $i < count($rows); $i++) {
        $h = (float)$rows[$i]['high']; $l = (float)$rows[$i]['low']; $pc = (float)$rows[$i - 1]['close'];
        $tr[] = max($h - $l, abs($h - $pc), abs($l - $pc));
    }
    $atr = array_sum(array_slice($tr, 0, 14)) / 14;
    for ($i = 14; $i < count($tr); $i++) $atr = ($atr * 13 + $tr[$i]) / 14;
    return $atr > 0 ? $atr : null;
}
function pf_exit_levels($ticker, $entry, $until_iso) {   // livelli in valuta del titolo; null se mancano dati
    $atr = pf_atr14($ticker, $until_iso);
    if ($atr === null || $entry <= 0) return null;
    return ['atr' => $atr, 'stop' => max(0.0, $entry - 1.5 * $atr), 'target' => $entry + 3 * $atr];
}
