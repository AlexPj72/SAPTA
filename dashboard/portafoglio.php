<?php
require_once 'config.php';
require_once 'helpers.php';
session_start();

// Lettura/scrittura PRIVATE: usa la chiave segreta e la password presenti solo sul server (config_secret.php, mai su GitHub).
$secret_ok = is_file(__DIR__ . '/config_secret.php');
if ($secret_ok) require_once __DIR__ . '/config_secret.php';
$pw_ok = $secret_ok && defined('PORTAFOGLIO_PASSWORD') && PORTAFOGLIO_PASSWORD !== '' && PORTAFOGLIO_PASSWORD !== 'SCEGLI_UNA_PASSWORD';

function pf_query($table, $params = []) {
    $ch = curl_init(SUPABASE_URL . '/rest/v1/' . $table . '?' . http_build_query($params));
    curl_setopt_array($ch, [CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => 15, CURLOPT_HTTPHEADER => [
        'apikey: ' . SUPABASE_SERVICE_KEY, 'Authorization: Bearer ' . SUPABASE_SERVICE_KEY]]);
    $body = curl_exec($ch);
    $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $cerr = curl_error($ch);
    curl_close($ch);
    $r = json_decode((string)$body, true);
    if ($code !== 200 || !is_array($r)) {
        $GLOBALS['pf_err'] = "HTTP $code " . $cerr . ' ' . substr(is_string($body) ? $body : '', 0, 200);
        return [];
    }
    return $r;
}
function pf_curve($rows, $init) {   // curva su base 100 con assi, griglia e valori al passaggio del mouse
    if (count($rows) < 2) return '<p class="muted">Curva disponibile dopo almeno due rilevazioni orarie.</p>';
    $tz = new DateTimeZone('Europe/Rome');
    $v = []; $lab = [];
    foreach ($rows as $r) {
        $v[] = (float)$r['equity_eur'] / $init * 100;
        $lab[] = (new DateTime($r['snapshot_at']))->setTimezone($tz)->format('d/m H:i');
    }
    $n = count($v);
    $min = min(min($v), 99.5); $max = max(max($v), 100.5);
    $pad = ($max - $min) * 0.1; $min -= $pad; $max += $pad;
    $W = 720; $H = 260; $L = 56; $R = 14; $T = 14; $B = 40;
    $pw = $W - $L - $R; $ph = $H - $T - $B; $span = max($max - $min, 0.0001);
    $X = fn($i) => round($L + $i / ($n - 1) * $pw, 1);
    $Y = fn($val) => round($T + ($max - $val) / $span * $ph, 1);
    $svg = '<svg viewBox="0 0 ' . $W . ' ' . $H . '" style="width:100%;height:auto;max-width:760px;color:inherit" font-size="11">';
    for ($k = 0; $k <= 4; $k++) {            // griglia e valori sull'asse y
        $val = $min + $span * $k / 4; $y = $Y($val);
        $svg .= '<line x1="' . $L . '" x2="' . ($W - $R) . '" y1="' . $y . '" y2="' . $y . '" stroke="currentColor" stroke-opacity=".15"/>'
              . '<text x="' . ($L - 6) . '" y="' . ($y + 4) . '" text-anchor="end" fill="currentColor" fill-opacity=".7">' . number_format($val, 2) . '</text>';
    }
    $y100 = $Y(100);                          // linea del capitale iniziale (base 100)
    $svg .= '<line x1="' . $L . '" x2="' . ($W - $R) . '" y1="' . $y100 . '" y2="' . $y100 . '" stroke="#c80" stroke-dasharray="5 4"/>'
          . '<text x="' . ($W - $R) . '" y="' . ($y100 - 4) . '" text-anchor="end" fill="#c80">capitale iniziale = 100</text>';
    $ticks = min(5, $n);                      // date sull'asse x
    for ($k = 0; $k < $ticks; $k++) {
        $i = (int) round($k * ($n - 1) / max($ticks - 1, 1)); $x = $X($i);
        $svg .= '<line x1="' . $x . '" x2="' . $x . '" y1="' . ($T + $ph) . '" y2="' . ($T + $ph + 4) . '" stroke="currentColor" stroke-opacity=".5"/>'
              . '<text x="' . $x . '" y="' . ($T + $ph + 18) . '" text-anchor="' . ($k === 0 ? 'start' : ($k === $ticks - 1 ? 'end' : 'middle')) . '" fill="currentColor" fill-opacity=".7">' . $lab[$i] . '</text>';
    }
    $pts = [];
    foreach ($v as $i => $val) $pts[] = $X($i) . ',' . $Y($val);
    $svg .= '<polyline fill="none" stroke="#2a7" stroke-width="2" points="' . implode(' ', $pts) . '"/>';
    foreach ($v as $i => $val) {              // punti con valore e data (tooltip)
        if ($n > 80 && $i % ceil($n / 80) !== 0 && $i !== $n - 1) continue;
        $svg .= '<circle cx="' . $X($i) . '" cy="' . $Y($val) . '" r="3.5" fill="#2a7"><title>' . $lab[$i] . ' — ' . number_format($val, 2) . ' (' . number_format($val * $init / 100, 2) . ' €)</title></circle>';
    }
    $svg .= '</svg>';
    return $svg . '<div class="muted">Ultimo valore: ' . number_format(end($v), 2) . ' (base 100) · ' . $lab[$n - 1] . ' ora italiana</div>';
}
function pf_rpc($fn, $args) {
    $ch = curl_init(SUPABASE_URL . '/rest/v1/rpc/' . $fn);
    curl_setopt_array($ch, [CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => 20, CURLOPT_POST => true,
        CURLOPT_POSTFIELDS => json_encode($args), CURLOPT_HTTPHEADER => ['Content-Type: application/json',
        'apikey: ' . SUPABASE_SERVICE_KEY, 'Authorization: Bearer ' . SUPABASE_SERVICE_KEY]]);
    $body = curl_exec($ch); $code = curl_getinfo($ch, CURLINFO_HTTP_CODE); curl_close($ch);
    $r = json_decode((string)$body, true);
    return [$code >= 200 && $code < 300, is_array($r) ? $r : [], $code, is_array($r) ? ($r['message'] ?? '') : (string)$body];
}
function pf_fees($market, $value_eur) {
    $rows = pf_query('costi_operazione', ['select' => '*', 'attivo' => 'eq.true']);
    foreach ($rows as $c) {
        if (($market === 'USA' && $c['broker'] === 'Alpaca' && $c['mercato'] === 'USA') || ($market === 'EU' && $c['broker'] === 'Interactive Brokers' && $c['mercato'] === 'EU'))
            return round((float)$c['commissione_fissa'] + $value_eur * ((float)$c['commissione_percentuale'] + (float)$c['bollo_percentuale']), 2);
    }
    return 0.0;
}
function pf_num($v) { return (float) str_replace(',', '.', trim((string)$v)); }

$mk = []; $msg = ''; $msg_err = false; $logged = !empty($_SESSION['pf_ok']);
if ($pw_ok && !$logged && isset($_POST['password'])) {
    if (hash_equals(PORTAFOGLIO_PASSWORD, (string)$_POST['password'])) { $_SESSION['pf_ok'] = true; $_SESSION['csrf'] = bin2hex(random_bytes(16)); header('Location: portafoglio.php'); exit; }
    $msg = 'Password errata'; $msg_err = true;
}
if ($pw_ok && $logged && empty($_SESSION['csrf'])) $_SESSION['csrf'] = bin2hex(random_bytes(16));
if ($pw_ok && $logged && isset($_GET['esci'])) { session_destroy(); header('Location: portafoglio.php'); exit; }

if ($pw_ok && $logged && $_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['azione'])) {
    if (!hash_equals($_SESSION['csrf'], (string)($_POST['csrf'] ?? ''))) { $msg = 'Sessione scaduta, riprova'; $msg_err = true; }
    else {
        $qty = pf_num($_POST['quantita'] ?? 0); $price = pf_num($_POST['prezzo'] ?? 0);
        $ticker = preg_replace('/[^A-Z0-9.\-]/', '', strtoupper((string)($_POST['ticker'] ?? '')));
        $market = ($_POST['mercato'] ?? '') === 'EU' ? 'EU' : 'USA';
        $cur = $market === 'EU' ? 'EUR' : 'USD';
        $fx = pf_num($_POST['fx'] ?? 1);
        if ($qty <= 0 || $price <= 0 || $fx <= 0 || $ticker === '') { $msg = 'Quantità, prezzo e ticker devono essere validi'; $msg_err = true; }
        else {
            $buy = $_POST['azione'] === 'compra';
            $lc = (int)($_POST['lifecycle_id'] ?? 0);
            $fees = pf_fees($market, $qty * $price * $fx);
            [$ok, $out, $code, $err] = pf_rpc('portfolio_execute_trade', [
                'p_code' => 'PORTAFOGLIO_UTENTE', 'p_ticker' => $ticker, 'p_side' => $buy ? 'BUY' : 'SELL', 'p_quantity' => $qty,
                'p_price_local' => $price, 'p_executed_at' => gmdate('c'),
                'p_idempotency_key' => $buy ? ('USER-BUY-' . $ticker . '-' . ($lc ?: gmdate('YmdHi'))) : ('USER-SELL-' . $ticker . '-' . gmdate('YmdHi')),
                'p_market' => $market, 'p_currency' => $cur, 'p_fx_eur_per_local' => $fx, 'p_fees_eur' => $fees,
                'p_price_reference' => $price, 'p_slippage_pct' => 0, 'p_source_type' => ($buy && $lc) ? 'LIFECYCLE' : 'MANUAL',
                'p_lifecycle_id' => $lc ?: null]);
            $msg = $ok ? (($out['duplicate'] ?? false) ? 'Operazione già registrata' : ($buy ? "Acquisto di $ticker registrato" : "Vendita di $ticker registrata")) : ('Operazione rifiutata: ' . $err);
            $msg_err = !$ok;
        }
    }
}

$sum = ($pw_ok && $logged) ? pf_query('v_portfolio_summary', ['select' => '*', 'order' => 'code.asc']) : [];
?>
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>SAPTA — Portafogli</title>
    <link rel="icon" href="assets/favicon.svg">
    <link rel="stylesheet" href="assets/style.css">
    <style>
        .wrap h2 { margin: 32px 0 12px; line-height: 1.3; }
        .wrap h3 { margin: 0 0 10px; }
        .wrap .card { margin: 14px 0; padding: 16px; overflow: hidden; }
        .wrap .stat-grid { margin: 12px 0; }
        .wrap .tw { overflow-x: auto; }
        .wrap table { width: 100%; border-collapse: collapse; }
        .wrap th, .wrap td { padding: 6px 10px; text-align: left; vertical-align: middle; border-bottom: 1px solid #e3e3e3; white-space: nowrap; }
        .wrap input[name=quantita], .wrap input[name=prezzo] { width: 80px; }
        .wrap .badge { display: inline-block; margin-left: 8px; padding: 2px 10px; border-radius: 10px; font-size: .6em; vertical-align: middle; background: #e6f4ea; }
        .wrap button { padding: 6px 12px; cursor: pointer; }
    </style>
</head>
<body>
<header class="hero compact">
    <div class="hero-top">
        <div>
            <div class="eyebrow">SAPTA v5.1.1 · simulazione PAPER</div>
            <h1>Portafogli</h1>
            <p>Il portafoglio dell'IA opera da solo; in quello dell'utente registri tu acquisti e vendite. Nessun ordine reale.</p>
        </div>
        <a class="back-link" href="index.php">← Dashboard</a>
    </div>
</header>
<?php render_nav('portafoglio.php'); ?>
<div class="wrap">
<?php if (!$secret_ok): ?>
    <div class="card"><p>Manca il file <b>config_secret.php</b> sul server: copia <code>config_secret.example.php</code> con la chiave service_role e la password.</p></div>
<?php elseif (!$pw_ok): ?>
    <div class="card"><p>In <b>config_secret.php</b> imposta <code>PORTAFOGLIO_PASSWORD</code> con una password tua: senza password la pagina resta chiusa.</p></div>
<?php elseif (!$logged): ?>
    <div class="card"><form method="post"><p>Password: <input type="password" name="password" autofocus> <button type="submit">Entra</button></p>
    <?php if ($msg): ?><p class="muted"><?= e($msg) ?></p><?php endif; ?></form></div>
<?php else: ?>
    <?php if ($msg): ?><div class="card"><p><b><?= $msg_err ? '⚠️ ' : '✅ ' ?><?= e($msg) ?></b></p></div><?php endif; ?>
    <p class="muted"><a href="portafoglio.php?esci=1">Esci</a></p>
    <?php if (!$sum): ?>
    <div class="card"><p>Nessun dato letto: controlla la chiave in config_secret.php.</p>
    <p class="muted">Dettaglio: <?= e($GLOBALS['pf_err'] ?? 'nessuna riga nella vista') ?></p></div>
    <?php else:
        $sig = pf_query('trade_lifecycle', ['select' => 'id,ticker,market,currency,entry_fill_price,quantity,fx_eur_per_local,invalidation_price,target_price,planned_time_exit_date,state,action_label,triggered_at', 'state' => 'in.(ENTRY_PENDING,ACTIVE)', 'order' => 'triggered_at.desc']);
    ?>
    <h2>Segnali operativi attivi (COMPRA ORA) <span class="badge"><?= count($sig) ?></span></h2>
    <div class="card">
    <?php if (!$sig): ?><p class="muted">Nessun segnale operativo attivo in questo momento. Il pulsante <b>Ho comprato</b> compare qui quando c'è un COMPRA ORA; <b>Ho venduto</b> compare accanto a ogni posizione aperta del portafoglio dell'utente.</p><?php else: ?>
        <div class="tw"><table><tr><th>Ticker</th><th>Prezzo</th><th>Stop</th><th>Obiettivo</th><th>Uscita entro</th><th>Quantità</th><th>Prezzo reale</th><th></th></tr>
        <?php foreach ($sig as $g): $mk[$g['market']] = true; ?>
            <?php $fid = 'fc' . (int)$g['id']; ?>
            <tr><td><a href="grafico.php?ticker=<?= urlencode($g['ticker']) ?>"><b><?= e($g['ticker']) ?></b></a>
                <form id="<?= $fid ?>" method="post"></form>
                <input form="<?= $fid ?>" type="hidden" name="csrf" value="<?= e($_SESSION['csrf']) ?>"><input form="<?= $fid ?>" type="hidden" name="azione" value="compra">
                <input form="<?= $fid ?>" type="hidden" name="ticker" value="<?= e($g['ticker']) ?>"><input form="<?= $fid ?>" type="hidden" name="mercato" value="<?= e($g['market']) ?>">
                <input form="<?= $fid ?>" type="hidden" name="fx" value="<?= e($g['fx_eur_per_local']) ?>"><input form="<?= $fid ?>" type="hidden" name="lifecycle_id" value="<?= (int)$g['id'] ?>"></td>
            <td><?= number_format((float)$g['entry_fill_price'], 2) ?></td>
            <td><?= number_format((float)$g['invalidation_price'], 2) ?></td><td><?= number_format((float)$g['target_price'], 2) ?></td>
            <td><?= e($g['planned_time_exit_date']) ?></td>
            <td><input form="<?= $fid ?>" name="quantita" size="5" value="<?= e(rtrim(rtrim(number_format((float)$g['quantity'], 4, '.', ''), '0'), '.')) ?>"></td>
            <td><input form="<?= $fid ?>" name="prezzo" size="7" value="<?= e(number_format((float)$g['entry_fill_price'], 2, '.', '')) ?>"></td>
            <td><button form="<?= $fid ?>" type="submit">Ho comprato</button></td></tr>
        <?php endforeach; ?></table></div>
        <p class="muted">Se hai comprato diversamente dal segnale, correggi quantità e prezzo prima di premere il pulsante.</p>
    <?php endif; ?></div>
    <?php endif; ?>
<?php endif; ?>
<?php foreach (($pw_ok && $logged) ? $sum : [] as $p):
    $code = $p['code']; $init = (float)$p['initial_capital_eur']; $eq = (float)$p['equity_eur'];
    $snap = pf_query('portfolio_snapshots', ['select' => 'snapshot_at,equity_eur', 'portfolio_id' => 'eq.' . $p['portfolio_id'], 'order' => 'snapshot_at.asc', 'limit' => 2000]);
    $pos = pf_query('v_portfolio_valuation', ['select' => '*', 'portfolio_code' => 'eq.' . $code, 'order' => 'ticker.asc']);
    $txs = pf_query('v_portfolio_history', ['select' => '*', 'portfolio_code' => 'eq.' . $code, 'tx_type' => 'in.(BUY,SELL)', 'order' => 'executed_at.desc', 'limit' => 30]);
    $idx = $init > 0 ? $eq / $init * 100 : 100;
?>
    <h2><?= e($p['name']) ?> <?= $p['trading_enabled'] ? '<span class="badge">attivo</span>' : '<span class="badge">non attivo</span>' ?></h2>
    <div class="stat-grid">
        <div class="stat-card"><div class="stat-label">Valore (base 100)</div><div class="stat-value"><?= number_format($idx, 2) ?></div><div class="stat-sub"><?= fmt_eur($eq) ?> su <?= fmt_eur($init) ?></div></div>
        <div class="stat-card"><div class="stat-label">Liquidità</div><div class="stat-value"><?= fmt_eur($p['cash_available_eur']) ?></div></div>
        <div class="stat-card"><div class="stat-label">P&amp;L realizzato</div><div class="stat-value"><?= fmt_eur($p['realized_pnl_eur']) ?></div></div>
        <div class="stat-card"><div class="stat-label">P&amp;L non realizzato</div><div class="stat-value"><?= fmt_eur($p['unrealized_pnl_eur']) ?></div></div>
        <div class="stat-card"><div class="stat-label">Costi pagati</div><div class="stat-value"><?= fmt_eur($p['fees_paid_eur']) ?></div></div>
    </div>
    <div class="card"><h3>Curva del capitale</h3><?= pf_curve($snap, $init) ?></div>
    <div class="card"><h3>Posizioni aperte (<?= count($pos) ?>)</h3>
    <?php if (!$pos): ?><p class="muted">Nessuna posizione aperta.</p><?php else: ?>
        <div class="tw"><table><tr><th>Ticker</th><th>Quantità</th><th>Costo</th><th>Valore</th><th>Risultato</th><th>Prezzo del</th><?php if ($code === 'PORTAFOGLIO_UTENTE'): ?><th>Vendita: quantità · prezzo</th><th></th><?php endif; ?></tr>
        <?php foreach ($pos as $r): $mk[$r['market']] = true; ?>
            <tr><td><a href="grafico.php?ticker=<?= urlencode($r['ticker']) ?>"><b><?= e($r['ticker']) ?></b></a></td><td><?= e(rtrim(rtrim(number_format((float)$r['quantity'], 4, '.', ''), '0'), '.')) ?></td>
            <td><?= fmt_eur($r['cost_basis_eur']) ?></td><td><?= fmt_eur($r['market_value_eur']) ?></td>
            <td><?= $r['unrealized_pnl_pct'] === null ? 'n.d.' : number_format((float)$r['unrealized_pnl_pct'], 2) . '%' ?></td>
            <td><?= e(substr((string)$r['price_as_of'], 0, 16)) ?></td>
            <?php if ($code === 'PORTAFOGLIO_UTENTE'): ?>
            <?php $fv = 'fv' . (int)$r['position_id']; ?>
            <td><form id="<?= $fv ?>" method="post"></form>
                <input form="<?= $fv ?>" type="hidden" name="csrf" value="<?= e($_SESSION['csrf']) ?>"><input form="<?= $fv ?>" type="hidden" name="azione" value="vendi">
                <input form="<?= $fv ?>" type="hidden" name="ticker" value="<?= e($r['ticker']) ?>"><input form="<?= $fv ?>" type="hidden" name="mercato" value="<?= e($r['market']) ?>"><input form="<?= $fv ?>" type="hidden" name="fx" value="<?= e($r['fx_eur_per_local_used']) ?>">
                <input form="<?= $fv ?>" name="quantita" size="5" value="<?= e(rtrim(rtrim(number_format((float)$r['quantity'], 4, '.', ''), '0'), '.')) ?>">
                <input form="<?= $fv ?>" name="prezzo" size="7" value="<?= e(number_format((float)$r['last_price_local'], 2, '.', '')) ?>"></td>
            <td><button form="<?= $fv ?>" type="submit">Ho venduto</button></td>
            <?php endif; ?></tr>
        <?php endforeach; ?></table></div>
    <?php endif; ?></div>
    <div class="card"><h3>Ultime operazioni</h3>
    <?php if (!$txs): ?><p class="muted">Nessuna operazione registrata.</p><?php else: ?>
        <div class="tw"><table><tr><th>Data (UTC)</th><th>Operazione</th><th>Ticker</th><th>Quantità</th><th>Prezzo</th><th>Costi</th><th>Risultato</th></tr>
        <?php foreach ($txs as $t): ?>
            <tr><td><?= e(substr((string)$t['executed_at'], 0, 16)) ?></td><td><?= $t['tx_type'] === 'BUY' ? 'COMPRATO' : 'VENDUTO' ?></td>
            <td><a href="grafico.php?ticker=<?= urlencode($t['ticker']) ?>"><?= e($t['ticker']) ?></a></td><td><?= e(rtrim(rtrim(number_format((float)$t['quantity'], 4, '.', ''), '0'), '.')) ?></td>
            <td><?= number_format((float)$t['price_local'], 2) ?> <?= $t['currency'] === 'USD' ? '$' : '€' ?></td>
            <td><?= fmt_eur($t['fees_eur']) ?></td><td><?= $t['tx_type'] === 'SELL' ? fmt_eur($t['realized_pnl_eur']) : '—' ?></td></tr>
        <?php endforeach; ?></table></div>
    <?php endif; ?></div>
<?php endforeach; ?>
<?php if ($pw_ok && $logged):
    $cmp = pf_query('stop_comparison', ['select' => '*', 'order' => 'lifecycle_id.asc']);
    $tf = 0; $td = 0; foreach ($cmp as $c) { $tf += (float)$c['fixed_net_eur']; $td += (float)$c['dynamic_net_eur']; }
    $sg = fn($x) => ($x >= 0 ? '+' : '−') . number_format(abs($x), 2, ',', '.') . ' €';
?>
    <h2>Confronto stop fisso / stop dinamico <span class="badge">simulazione</span></h2>
    <div class="card">
    <?php if (!$cmp): ?><p class="muted">Nessuna operazione da confrontare.</p><?php else: ?>
        <div class="tw"><table><tr><th>Ticker</th><th>Stop fisso (regole attuali)</th><th>Stop dinamico</th><th>Differenza</th></tr>
        <?php foreach ($cmp as $c): ?>
            <tr><td><a href="grafico.php?ticker=<?= urlencode($c['ticker']) ?>"><?= e($c['ticker']) ?></a><?= !empty($c['storico']) ? ' <span class="muted">(storico, prima del portafoglio)</span>' : '' ?></td>
            <td><?= e($c['fixed_reason']) ?> · <?= $sg((float)$c['fixed_net_eur']) ?></td>
            <td><?= e($c['dynamic_reason']) ?> · <?= $sg((float)$c['dynamic_net_eur']) ?></td>
            <td><?= $sg((float)$c['dynamic_net_eur'] - (float)$c['fixed_net_eur']) ?></td></tr>
        <?php endforeach; ?>
            <tr><td><b>Totale netto</b></td><td><b><?= $sg($tf) ?></b></td><td><b><?= $sg($td) ?></b></td><td><b><?= $sg($td - $tf) ?></b></td></tr>
        </table></div>
        <p class="muted">Stesso ingresso, commissioni, slippage e uscita a 5 sedute in entrambi. Le posizioni APERTE sono valutate all'ultimo prezzo. Non modifica le regole né i portafogli.</p>
    <?php endif; ?></div>
<?php endif; ?>
</div>
<?php if ($pw_ok && $logged): ?>
<p class="muted" style="text-align:center">Pagina aggiornata alle <?= (new DateTime('now', new DateTimeZone('Europe/Rome')))->format('H:i:s') ?> (ora italiana) · <span id="aggiorna">…</span></p>
<script>
// Ricarica automatica ogni 5 minuti SOLO se e' aperta la borsa di almeno uno dei titoli mostrati (EU 9:00-17:30 ora di Milano,
// USA 9:30-16:00 ora di New York, con 10 minuti di margine per l'ultima candela; sabato e domenica chiuso; le festivita' non sono considerate).
var MERCATI = <?= json_encode(array_keys($mk) ?: ['EU', 'USA']) ?>;
function borsaAperta(m) {
    var tz = (m === 'EU') ? 'Europe/Rome' : 'America/New_York', g = {};
    new Intl.DateTimeFormat('en-GB', {timeZone: tz, weekday: 'short', hour: '2-digit', minute: '2-digit', hour12: false})
        .formatToParts(new Date()).forEach(function (x) { g[x.type] = x.value; });
    if (g.weekday === 'Sat' || g.weekday === 'Sun') return false;
    var min = (parseInt(g.hour, 10) % 24) * 60 + parseInt(g.minute, 10);
    return (m === 'EU') ? (min >= 540 && min < 1050 + 10) : (min >= 570 && min < 960 + 10);
}
function almenoUnaAperta() { return MERCATI.some(borsaAperta); }
document.getElementById('aggiorna').textContent = almenoUnaAperta()
    ? 'borsa aperta: si ricarica da sola ogni 5 minuti' : 'borse chiuse: nessun aggiornamento automatico';
setInterval(function () {
    var a = document.activeElement;
    if (a && (a.name === 'quantita' || a.name === 'prezzo')) return;   // non perdere quanto stai scrivendo
    if (almenoUnaAperta()) location.href = location.pathname;           // GET, mai un nuovo invio di moduli
}, 300000);
</script>
<?php endif; ?>
</body>
</html>
