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
function pf_curve($rows, $init) {   // curva su base 100, SVG
    if (count($rows) < 2) return '<p class="muted">Curva disponibile dopo almeno due rilevazioni orarie.</p>';
    $v = array_map(fn($r) => (float)$r['equity_eur'] / $init * 100, $rows);
    $min = min(min($v), 99); $max = max(max($v), 101);
    $w = 640; $h = 140; $pts = [];
    foreach ($v as $i => $y) $pts[] = round($i / (count($v) - 1) * $w, 1) . ',' . round($h - ($y - $min) / max($max - $min, 0.01) * $h, 1);
    $base = round($h - (100 - $min) / max($max - $min, 0.01) * $h, 1);
    return '<svg viewBox="0 0 ' . $w . ' ' . $h . '" style="width:100%;height:auto"><line x1="0" x2="' . $w . '" y1="' . $base . '" y2="' . $base .
        '" stroke="#999" stroke-dasharray="4"/><polyline fill="none" stroke="#2a7" stroke-width="2" points="' . implode(' ', $pts) . '"/></svg>' .
        '<div class="muted">Ultimo valore: ' . number_format(end($v), 2) . ' (base 100)</div>';
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

$msg = ''; $msg_err = false; $logged = !empty($_SESSION['pf_ok']);
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
        <?php foreach ($sig as $g): ?>
            <?php $fid = 'fc' . (int)$g['id']; ?>
            <tr><td><b><?= e($g['ticker']) ?></b>
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
        <?php foreach ($pos as $r): ?>
            <tr><td><?= e($r['ticker']) ?></td><td><?= e(rtrim(rtrim(number_format((float)$r['quantity'], 4, '.', ''), '0'), '.')) ?></td>
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
            <td><?= e($t['ticker']) ?></td><td><?= e(rtrim(rtrim(number_format((float)$t['quantity'], 4, '.', ''), '0'), '.')) ?></td>
            <td><?= number_format((float)$t['price_local'], 2) ?> <?= $t['currency'] === 'USD' ? '$' : '€' ?></td>
            <td><?= fmt_eur($t['fees_eur']) ?></td><td><?= $t['tx_type'] === 'SELL' ? fmt_eur($t['realized_pnl_eur']) : '—' ?></td></tr>
        <?php endforeach; ?></table></div>
    <?php endif; ?></div>
<?php endforeach; ?>
</div>
</body>
</html>
