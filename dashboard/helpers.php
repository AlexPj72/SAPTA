<?php
/**
 * Helper condivisi per tutte le pagine della dashboard SAPTA.
 * [NUOVO 16/09] Contiene anche spiega_segnale(): traduce i punteggi
 * numerici (H2, contesto, GDELT, rischio) in una spiegazione testuale
 * leggibile - risposta alla richiesta di "alert spiegati" e guida al
 * paper trading. Non introduce nuovi dati: legge solo campi già scritti
 * dalla pipeline Python (screening_candidates, signals_filtered).
 */

function e($value) {
    return htmlspecialchars((string) $value, ENT_QUOTES, 'UTF-8');
}

function fmt_eur($v, $dec = 2) {
    return $v === null ? '—' : '€' . number_format((float) $v, $dec);
}

function fmt_pct($v, $dec = 2) {
    return $v === null ? '—' : number_format(((float) $v) * 100, $dec) . '%';
}

/** Barra di navigazione condivisa - stessa su tutte le pagine. */
function render_nav($active) {
    $items = [
        'index.php'     => 'Dashboard',
        'universo.php'  => 'Universo',
        'anomalies.php' => 'Radar anomalie',
        'signals.php'   => 'Segnali grezzi',
        'decisions.php' => 'Paper trading',
        'capital.php'   => 'Capitale',
    ];
    echo '<nav class="nav-bar">';
    foreach ($items as $href => $label) {
        $cls = ($href === $active) ? ' class="active"' : '';
        echo "<a href=\"$href\"$cls>" . e($label) . "</a>";
    }
    echo '</nav>';
}

/** Badge colorato per un'azione BUY/SELL/HOLD. */
function badge_azione($azione) {
    $azione = strtoupper((string) $azione);
    $cls = $azione === 'BUY' ? 'buy' : ($azione === 'SELL' ? 'sell' : 'hold');
    return '<span class="badge ' . $cls . '">' . e($azione) . '</span>';
}

/** Pillola colorata per il final_rank_score (0-100, Sezione 16). */
function rank_pill($score) {
    if ($score === null) return '<span class="muted">—</span>';
    $score = (float) $score;
    $cls = $score >= 60 ? 'r-high' : ($score >= 35 ? 'r-mid' : 'r-low');
    return '<span class="rank-pill ' . $cls . '">' . round($score) . '</span>';
}

/** Sparkline SVG minimale da una serie di prezzi. */
function sparkline_svg($rows) {
    if (count($rows) < 2) return '<span class="spark-empty">—</span>';
    $rows = array_reverse($rows);
    $values = array_map(fn($r) => (float) $r['close'], $rows);
    $min = min($values); $max = max($values);
    $range = ($max - $min) ?: 1;
    $w = 100; $h = 30; $pad = 2;
    $points = [];
    $n = count($values);
    foreach ($values as $i => $v) {
        $x = $pad + ($i / max(1, $n - 1)) * ($w - 2 * $pad);
        $y = $h - $pad - (($v - $min) / $range) * ($h - 2 * $pad);
        $points[] = round($x, 1) . ',' . round($y, 1);
    }
    $first = $values[0]; $last = $values[count($values) - 1];
    $class = $last >= $first ? 'spark-up' : 'spark-down';
    return '<svg class="sparkline ' . $class . '" viewBox="0 0 ' . $w . ' ' . $h . '" role="img" aria-label="Andamento">'
         . '<polyline points="' . e(implode(' ', $points)) . '" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
}

/**
 * [NUOVO 16/09 - risposta alla richiesta di alert spiegati]
 * Costruisce una spiegazione in linguaggio naturale di un'opportunità,
 * combinando: tipologia, confidenza, rendimento netto, contesto tecnico
 * (trend/GDELT, dentro context_score), rischio di portafoglio (Sezione 15)
 * e qualità del dato. Non inventa nulla: ogni frase è condizionata
 * all'esistenza del campo corrispondente nel record.
 *
 * $signal: riga di signals_filtered
 * $candidate: riga corrispondente di screening_candidates (opzionale, per
 *             anomaly_score/context_score/news_light_count)
 */
function spiega_segnale($signal, $candidate = null) {
    $parti = [];

    $azione = strtoupper($signal['filtered_action'] ?? $signal['original_action'] ?? 'HOLD');
    $tipo = $signal['opportunity_type'] ?? null;
    $conf = $signal['confidence_level'] ?? null;

    if ($azione === 'HOLD') {
        $motivo = $signal['filter_reason'] ?? null;
        if ($motivo) {
            return "<b>Nessuna azione.</b> " . e($motivo) . ".";
        }
        return "<b>Nessuna azione.</b> Il segnale originale era già HOLD, nessuna anomalia operativa rilevata.";
    }

    $verbo = $azione === 'BUY' ? 'Segnale di acquisto' : 'Segnale di vendita';
    $frase = "<b>$verbo";
    if ($tipo) $frase .= " (" . e($tipo) . ")";
    $frase .= ".</b> ";
    $parti[] = $frase;

    if ($conf) {
        $conf_txt = ['alto' => 'alta', 'medio' => 'media', 'basso' => 'bassa'][$conf] ?? $conf;
        $parti[] = "Confidenza del verdetto: <b>$conf_txt</b>.";
    }

    if (isset($signal['expected_net_return'])) {
        $ret = (float) $signal['expected_net_return'];
        $parti[] = "Rendimento netto atteso (dopo costi e slippage): <b>" . fmt_pct($ret) . "</b>"
                 . ($ret > 0 ? " — positivo anche a costi inclusi." : " — attenzione, vicino/sotto soglia.");
    }

    if ($candidate && isset($candidate['context_score']) && $candidate['context_score'] !== null) {
        $ctx = (float) $candidate['context_score'];
        if ($ctx > 0.15) {
            $parti[] = "Il contesto (trend di medio periodo + clima economico/geopolitico via GDELT) è <b>favorevole</b>.";
        } elseif ($ctx < -0.15) {
            $parti[] = "Il contesto (trend di medio periodo + clima economico/geopolitico via GDELT) è <b>sfavorevole</b> — il segnale va contro il quadro generale, valuta con più cautela.";
        } else {
            $parti[] = "Il contesto di fondo (trend, clima macro/geopolitico) è sostanzialmente <b>neutro</b>.";
        }
    }

    if ($candidate && isset($candidate['news_light_count']) && $candidate['news_light_count'] !== null) {
        $n = (int) $candidate['news_light_count'];
        if ($n > 0) {
            $parti[] = "Ci sono <b>$n notizie recenti</b> collegate al titolo — vale la pena controllarle prima di decidere.";
        }
    }

    if (isset($signal['sector_concentration_count']) && $signal['sector_concentration_count']) {
        $parti[] = "Attenzione: hai già <b>{$signal['sector_concentration_count']}</b> posizioni nello stesso settore.";
    }
    if (isset($signal['portfolio_exposure_pct']) && $signal['portfolio_exposure_pct'] !== null && (float)$signal['portfolio_exposure_pct'] > 0.3) {
        $parti[] = "Esposizione stimata di portafoglio se eseguita: <b>" . fmt_pct($signal['portfolio_exposure_pct'], 0) . "</b> del capitale.";
    }

    if (isset($signal['target_price']) || isset($signal['invalidation_price'])) {
        $tp = isset($signal['target_price']) ? fmt_eur($signal['target_price']) : '—';
        $ip = isset($signal['invalidation_price']) ? fmt_eur($signal['invalidation_price']) : '—';
        $parti[] = "Livelli: obiettivo (target) $tp, invalidazione (stop) $ip.";
    }

    return implode(' ', $parti);
}
