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

/** [FIX 24/09 - audit] Concorda singolare/plurale per un conteggio,
 * es. plural_it(1, 'ricontrollo', 'ricontrolli') => "1 ricontrollo",
 * plural_it(4, 'ricontrollo', 'ricontrolli') => "4 ricontrolli". */
function plural_it($count, $singular, $plural) {
    return $count . ' ' . (((int) $count) === 1 ? $singular : $plural);
}

/** Barra di navigazione condivisa - stessa su tutte le pagine. */
function render_nav($active) {
    $items = [
        'index.php'     => 'Dashboard',
        'today.php'     => '🎯 Da valutare',
        'briefing.php'  => 'Briefing',
        'universo.php'  => 'Universo',
        'anomalies.php' => 'Radar anomalie',
        'signals.php'   => 'Segnali grezzi',
        'decisions.php' => 'Paper trading',
        'chat.php'      => 'Chat AI',
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

/**
 * [NUOVO 19/09 - Punto 4] Versione PHP dello stesso calcolo di
 * src/market_context.py::get_market_direction() - letto qui via Supabase
 * invece che duplicare la scrittura, entrambi leggono la stessa tabella
 * 'prezzi' popolata da modulo_a_ingestion.py (ticker '^GSPC'/'FTSEMIB.MI').
 */
function get_market_direction_dashboard() {
    $result = ['usa' => null, 'italia' => null];
    $index_map = ['^GSPC' => 'usa', 'FTSEMIB.MI' => 'italia'];
    foreach ($index_map as $ticker => $key) {
        $rows = supabase_query('prezzi', [
            'select' => 'close,timestamp', 'ticker' => 'eq.' . $ticker, 'interval' => 'eq.15m',
            'order' => 'timestamp.desc', 'limit' => 40,
        ]);
        if (count($rows) < 2) continue;
        $last_date = substr($rows[0]['timestamp'], 0, 10);
        $same_day = array_values(array_filter($rows, fn($r) => substr($r['timestamp'], 0, 10) === $last_date));
        if (count($same_day) < 2) continue;
        $latest = (float) $same_day[0]['close'];
        $first = (float) end($same_day)['close'];
        $result[$key] = round(($latest / $first - 1) * 100, 2);
    }
    return $result;
}

function market_direction_badge($pct, $label) {
    if ($pct === null) return "<span class=\"muted\">$label: dato non disponibile</span>";
    $cls = $pct > 0.15 ? 'positive' : ($pct < -0.15 ? 'negative' : 'muted');
    $sign = $pct >= 0 ? '+' : '';
    return "<span class=\"$cls\">$label: {$sign}{$pct}%</span>";
}

/**
 * [NUOVO 18/09] Bandiera del mercato di un ticker. Universo SAPTA copre
 * solo USA (nessun suffisso) e Italia/Milano (suffisso .MI) - nessun
 * titolo di Londra o altre piazze europee al momento, quindi solo 2 casi.
 */
function market_flag($ticker) {
    if (str_ends_with($ticker, '.MI')) return '🇮🇹';
    return '🇺🇸';
}

/**
 * [NUOVO 18/09] Stato approssimativo del mercato (aperto/chiuso), solo per
 * dare un'indicazione visiva - NON tiene conto di festività locali, solo
 * degli orari standard. USA: 13:30-20:00 UTC (EDT); Italia: 07:00-15:30 UTC
 * (CEST) - questi orari si spostano di un'ora con l'ora legale/solare.
 */
function market_status($ticker) {
    $is_it = str_ends_with($ticker, '.MI');
    $now_utc = (int) gmdate('Hi'); // es. 1345 per le 13:45 UTC
    $weekday = (int) gmdate('N'); // 1=lunedì … 7=domenica
    if ($weekday >= 6) return ['aperto' => false, 'label' => 'chiuso (weekend)'];
    if ($is_it) {
        $aperto = $now_utc >= 700 && $now_utc < 1530;
    } else {
        $aperto = $now_utc >= 1330 && $now_utc < 2000;
    }
    return ['aperto' => $aperto, 'label' => $aperto ? 'aperto ora (indicativo)' : 'chiuso ora (indicativo)'];
}

/**
 * [NUOVO 17/09 - Fase 2 SAPTA v6] Tool layer minimale per la Chat AI.
 * Invece di passare un contesto fisso (approccio precedente, troppo
 * "passivo" - la chat poteva solo commentare dati già pronti), la chat ora
 * può CHIEDERE dati freschi via function calling Gemini. Ogni tool esegue
 * una query reale su Supabase - nessun dato inventato, mai.
 */
function chat_tools_schema() {
    return [[
        'functionDeclarations' => [
            [
                'name' => 'get_universe_movers',
                'description' => "Ritorna i titoli dell'universo con la maggiore variazione (positiva o negativa) rispetto alla chiusura precedente, con settore e volume. Usa questo per rispondere a domande tipo 'quali titoli si muovono di più oggi' o 'quali titoli sono in gap'.",
                'parameters' => ['type' => 'OBJECT', 'properties' => [
                    'market' => ['type' => 'STRING', 'description' => "Filtra per mercato: 'IT' o 'USA'. Omesso = tutti."],
                    'limit' => ['type' => 'INTEGER', 'description' => 'Numero massimo di titoli da restituire, default 15'],
                ]],
            ],
            [
                'name' => 'get_ticker_detail',
                'description' => "Ritorna il dettaglio completo di UN singolo ticker: ultime chiusure giornaliere, ultime barre intraday se disponibili, settore, tono GDELT del paese, earnings imminenti, ultimo candidato screening (H1/H2) ed eventuale ultimo segnale filtrato (Modulo E). Usa questo quando l'utente chiede di un titolo specifico.",
                'parameters' => ['type' => 'OBJECT', 'properties' => [
                    'ticker' => ['type' => 'STRING', 'description' => 'Il ticker esatto, es. AAPL o ENI.MI'],
                ], 'required' => ['ticker']],
            ],
            [
                'name' => 'get_screening_activity_today',
                'description' => "Ritorna tutti i candidati rilevati oggi da H1/H2 (radar anomalie), anche quelli poi scartati - non solo i segnali BUY/SELL finali. Usa questo per 'cosa ha rilevato il radar oggi' o quando i segnali finali sono pochi/assenti ma vuoi sapere se qualcosa si è comunque mosso.",
                'parameters' => ['type' => 'OBJECT', 'properties' => new stdClass()],
            ],
            [
                'name' => 'get_sector_peers',
                'description' => "Ritorna tutti i titoli di un settore con la variazione di oggi, per confrontare la forza relativa di un titolo rispetto ai suoi simili.",
                'parameters' => ['type' => 'OBJECT', 'properties' => [
                    'sector' => ['type' => 'STRING', 'description' => "Nome del settore, es. 'Technology', 'Financials'. Se non sai il nome esatto, prima chiama get_ticker_detail sul titolo di interesse per leggerlo."],
                ], 'required' => ['sector']],
            ],
        ],
    ]];
}

function chat_tool_universe_movers($market = null, $limit = 15) {
    $changes = []; // ticker => ['chg_1d'=>..,'sector'=>..,'market'=>..]
    $prezzi = supabase_query('prezzi', ['select' => 'ticker,timestamp,close', 'interval' => 'eq.1d', 'order' => 'timestamp.desc', 'limit' => 3000]);
    $by_ticker = [];
    foreach ($prezzi as $r) {
        $t = $r['ticker'] ?? '';
        if ($t === '' || $r['close'] === null) continue;
        $by_ticker[$t] = $by_ticker[$t] ?? [];
        if (count($by_ticker[$t]) < 2) $by_ticker[$t][] = (float) $r['close'];
    }
    $sectors = supabase_query('ticker_sectors', ['select' => 'ticker,sector']);
    $sector_map = [];
    foreach ($sectors as $s) $sector_map[$s['ticker']] = $s['sector'] ?? null;

    foreach ($by_ticker as $t => $closes) {
        if (count($closes) < 2) continue;
        $is_it = str_ends_with($t, '.MI');
        if ($market === 'IT' && !$is_it) continue;
        if ($market === 'USA' && $is_it) continue;
        $changes[$t] = [
            'ticker' => $t,
            'chg_1d_pct' => round(($closes[0] / $closes[1] - 1) * 100, 2),
            'sector' => $sector_map[$t] ?? null,
        ];
    }
    usort($changes, fn($a, $b) => abs($b['chg_1d_pct']) <=> abs($a['chg_1d_pct']));
    return array_slice(array_values($changes), 0, $limit ?: 15);
}

function chat_tool_ticker_detail($ticker) {
    $ticker = strtoupper(trim($ticker));
    $daily = supabase_query('prezzi', ['select' => 'timestamp,close,volume', 'ticker' => 'eq.' . $ticker, 'interval' => 'eq.1d', 'order' => 'timestamp.desc', 'limit' => 5]);
    $intraday = supabase_query('prezzi', ['select' => 'timestamp,close,volume', 'ticker' => 'eq.' . $ticker, 'interval' => 'eq.15m', 'order' => 'timestamp.desc', 'limit' => 10]);
    $sector_rows = supabase_query('ticker_sectors', ['select' => 'sector', 'ticker' => 'eq.' . $ticker, 'limit' => 1]);
    $candidate = supabase_query('screening_candidates', ['select' => '*', 'ticker' => 'eq.' . $ticker, 'order' => 'timestamp.desc', 'limit' => 1]);
    $signal = supabase_query('signals_filtered', ['select' => '*', 'ticker' => 'eq.' . $ticker, 'order' => 'timestamp.desc', 'limit' => 1]);

    if (empty($daily) && empty($intraday)) {
        return ['errore' => "Nessun dato trovato per '$ticker' - verifica che il ticker sia scritto esattamente come nell'universo SAPTA (es. suffisso .MI per Milano)."];
    }
    return [
        'ticker' => $ticker,
        'settore' => $sector_rows[0]['sector'] ?? null,
        'ultime_chiusure_giornaliere' => $daily,
        'ultime_barre_15m' => $intraday,
        'ultimo_candidato_screening_H1_H2' => $candidate[0] ?? null,
        'ultimo_segnale_modulo_E' => $signal[0] ?? null,
    ];
}

function chat_tool_screening_today() {
    $today = date('Y-m-d');
    $rows = supabase_query('screening_candidates', ['select' => '*', 'timestamp' => 'gte.' . $today . 'T00:00:00', 'order' => 'timestamp.desc', 'limit' => 50]);
    return $rows ?: ['nota' => "Nessun candidato rilevato da H1/H2 oggi finora."];
}

function chat_tool_sector_peers($sector) {
    $tickers = supabase_query('ticker_sectors', ['select' => 'ticker', 'sector' => 'eq.' . $sector]);
    $ticker_list = array_map(fn($t) => $t['ticker'], $tickers);
    if (!$ticker_list) return ['errore' => "Nessun ticker trovato per il settore '$sector'."];
    $movers = chat_tool_universe_movers(null, 200);
    return array_values(array_filter($movers, fn($m) => in_array($m['ticker'], $ticker_list, true)));
}

function chat_tool_dispatch($name, $args) {
    try {
        switch ($name) {
            case 'get_universe_movers':
                return chat_tool_universe_movers($args['market'] ?? null, $args['limit'] ?? 15);
            case 'get_ticker_detail':
                return chat_tool_ticker_detail($args['ticker'] ?? '');
            case 'get_screening_activity_today':
                return chat_tool_screening_today();
            case 'get_sector_peers':
                return chat_tool_sector_peers($args['sector'] ?? '');
            default:
                return ['errore' => "Tool sconosciuto: $name"];
        }
    } catch (Exception $e) {
        return ['errore' => 'Errore interno nel recupero dati: ' . $e->getMessage()];
    }
}

/**
 * [NUOVO 17/09] Chiamata a Gemini con function calling (tool layer).
 * $history: array di ['role'=>'user'|'model'|'function', 'text'=>...] oppure
 * turni già strutturati (functionCall/functionResponse) - qui semplificato
 * a testo per i turni utente/modello, con gestione separata delle chiamate
 * a funzione nel loop sottostante. Max 4 round di tool-use per risposta,
 * poi si ferma e risponde con quello che ha (mai un loop infinito).
 */
function gemini_chat_with_tools($history) {
    // [FIX 26/09] Usa la chiave dedicata se configurata, altrimenti quella
    // condivisa con i moduli automatici (comportamento invariato se
    // GEMINI_CHAT_API_KEY è lasciata vuota in config.php).
    $api_key = GEMINI_CHAT_API_KEY ?: GEMINI_API_KEY;
    if (!$api_key) return null;

    $contents = array_map(fn($h) => ['role' => $h['role'], 'parts' => [['text' => $h['text']]]], $history);
    $max_rounds = 4;

    for ($round = 0; $round < $max_rounds; $round++) {
        $ch = curl_init('https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent');
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_POST, true);
        curl_setopt($ch, CURLOPT_HTTPHEADER, ['x-goog-api-key: ' . $api_key, 'Content-Type: application/json']);
        curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode(['contents' => $contents, 'tools' => chat_tools_schema()]));
        curl_setopt($ch, CURLOPT_TIMEOUT, 30);
        $response = curl_exec($ch);
        $http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);

        if ($http_code !== 200) return null;
        $data = json_decode($response, true);
        $parts = $data['candidates'][0]['content']['parts'] ?? null;
        if (!$parts) return null;

        $function_calls = array_filter($parts, fn($p) => isset($p['functionCall']));
        if (empty($function_calls)) {
            // Nessuna richiesta di tool: è la risposta finale testuale
            return $parts[0]['text'] ?? null;
        }

        // Il modello ha chiesto uno o più tool: eseguiamo e rispondiamo nello stesso turno
        $contents[] = ['role' => 'model', 'parts' => array_values($function_calls)];
        $function_response_parts = [];
        foreach ($function_calls as $fc) {
            $name = $fc['functionCall']['name'];
            $args = $fc['functionCall']['args'] ?? [];
            $result = chat_tool_dispatch($name, $args);
            $function_response_parts[] = ['functionResponse' => ['name' => $name, 'response' => ['result' => $result]]];
        }
        $contents[] = ['role' => 'function', 'parts' => $function_response_parts];
    }

    return "Ho provato a raccogliere dati ma servono troppe verifiche per questa domanda — puoi essere più specifico (es. un singolo ticker)?";
}



/**
 * [AGGIORNATO 17/09 - Fase 2 SAPTA v6] Messaggio di sistema per la Chat AI.
 * Non porta più tutti i dati pre-caricati (approccio precedente, troppo
 * limitato) - dà solo un orientamento minimo (capitale, che il briefing
 * esiste) e le istruzioni su come usare i tool per andare a recuperare
 * dati veri quando servono. Elimina esplicitamente la formulazione
 * "non dispongo di analisi previsionali" in favore di una spiegazione del
 * limite reale che non blocca comunque l'analisi.
 */
function build_chat_context() {
    $capital_rows = supabase_query('capital_state', ['select' => 'capital_eur', 'order' => 'created_at.desc', 'limit' => 1]);
    $capital = $capital_rows[0]['capital_eur'] ?? null;
    $today = date('Y-m-d');
    $has_briefing = count(supabase_query('daily_briefing', ['select' => 'id', 'briefing_date' => 'eq.' . $today, 'limit' => 1])) > 0;

    return "Sei l'analista pre-market di SAPTA, un sistema di analisi e screening titoli (non un sistema di trading automatico). Rispondi in italiano, in modo diretto e concreto.\n\n"
        . "REGOLE FONDAMENTALI:\n"
        . "- Hai accesso a strumenti (function calling) per leggere dati REALI da Supabase: get_universe_movers, get_ticker_detail, get_screening_activity_today, get_sector_peers. USALI attivamente per rispondere - non limitarti a commentare a vuoto, vai a cercare il dato.\n"
        . "- Non inventare MAI prezzi, notizie o dati che non hai recuperato con un tool.\n"
        . "- Non esiste un sistema in grado di sapere con certezza quali titoli faranno +2%/+3%/+4% prima dell'apertura - se te lo chiedono, NON rispondere semplicemente 'non dispongo di analisi previsionali': spiega il perché in una frase, poi USA I TOOL per fare comunque un'analisi sistematica (es. get_universe_movers per vedere i titoli più mossi, get_screening_activity_today per le anomalie rilevate) e proponi una shortlist ragionata, dichiarando che è un'ipotesi qualitativa e non una certezza.\n"
        . "- Distingui sempre dato osservato (es. 'volume 3.5x la media') da interpretazione ('questo può indicare interesse anomalo') da ipotesi ('potrebbe continuare, non è un fatto').\n"
        . "- Se una domanda riguarda un titolo specifico, chiama sempre get_ticker_detail su quel ticker prima di rispondere.\n\n"
        . "Contesto minimo: capitale operativo " . ($capital !== null ? fmt_eur($capital) : 'non impostato')
        . ($has_briefing ? "; è disponibile il briefing pre-apertura di oggi (chiedimelo se vuoi che lo consulti)." : "; nessun briefing generato oggi.");
}
