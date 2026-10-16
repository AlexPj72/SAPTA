<?php
require_once 'config.php';
require_once 'helpers.php';

// Lettura PRIVATA dei portafogli: usa la chiave segreta presente solo sul server (config_secret.php, mai su GitHub).
$secret_ok = is_file(__DIR__ . '/config_secret.php');
if ($secret_ok) require_once __DIR__ . '/config_secret.php';

function pf_query($table, $params = []) {
    $ch = curl_init(SUPABASE_URL . '/rest/v1/' . $table . '?' . http_build_query($params));
    curl_setopt_array($ch, [CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => 15, CURLOPT_HTTPHEADER => [
        'apikey: ' . SUPABASE_SERVICE_KEY, 'Authorization: Bearer ' . SUPABASE_SERVICE_KEY]]);
    $r = json_decode(curl_exec($ch), true);
    curl_close($ch);
    return is_array($r) && !isset($r['message']) ? $r : [];
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

$sum = $secret_ok ? pf_query('v_portfolio_summary', ['select' => '*', 'order' => 'code.asc']) : [];
?>
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>SAPTA — Portafogli</title>
    <link rel="icon" href="assets/favicon.svg">
    <link rel="stylesheet" href="assets/style.css">
</head>
<body>
<header class="hero compact">
    <div class="hero-top">
        <div>
            <div class="eyebrow">SAPTA v5.1.1 · simulazione PAPER</div>
            <h1>Portafogli</h1>
            <p>Il portafoglio dell'IA opera da solo; quello dell'utente registra le tue decisioni. Nessun ordine reale.</p>
        </div>
        <a class="back-link" href="index.php">← Dashboard</a>
    </div>
</header>
<?php render_nav('portafoglio.php'); ?>
<div class="wrap">
<?php if (!$secret_ok): ?>
    <div class="card"><p>Manca il file <b>config_secret.php</b> sul server: copia <code>config_secret.example.php</code> con la chiave service_role.</p></div>
<?php elseif (!$sum): ?>
    <div class="card"><p>Nessun dato letto: controlla la chiave in config_secret.php.</p></div>
<?php endif; ?>
<?php foreach ($sum as $p):
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
        <table><tr><th>Ticker</th><th>Quantità</th><th>Costo</th><th>Valore</th><th>Risultato</th><th>Prezzo del</th></tr>
        <?php foreach ($pos as $r): ?>
            <tr><td><?= e($r['ticker']) ?></td><td><?= e(rtrim(rtrim(number_format((float)$r['quantity'], 4, '.', ''), '0'), '.')) ?></td>
            <td><?= fmt_eur($r['cost_basis_eur']) ?></td><td><?= fmt_eur($r['market_value_eur']) ?></td>
            <td><?= $r['unrealized_pnl_pct'] === null ? 'n.d.' : number_format((float)$r['unrealized_pnl_pct'], 2) . '%' ?></td>
            <td><?= e(substr((string)$r['price_as_of'], 0, 16)) ?></td></tr>
        <?php endforeach; ?></table>
    <?php endif; ?></div>
    <div class="card"><h3>Ultime operazioni</h3>
    <?php if (!$txs): ?><p class="muted">Nessuna operazione registrata.</p><?php else: ?>
        <table><tr><th>Data (UTC)</th><th>Operazione</th><th>Ticker</th><th>Quantità</th><th>Prezzo</th><th>Costi</th><th>Risultato</th></tr>
        <?php foreach ($txs as $t): ?>
            <tr><td><?= e(substr((string)$t['executed_at'], 0, 16)) ?></td><td><?= $t['tx_type'] === 'BUY' ? 'COMPRATO' : 'VENDUTO' ?></td>
            <td><?= e($t['ticker']) ?></td><td><?= e(rtrim(rtrim(number_format((float)$t['quantity'], 4, '.', ''), '0'), '.')) ?></td>
            <td><?= number_format((float)$t['price_local'], 2) ?> <?= $t['currency'] === 'USD' ? '$' : '€' ?></td>
            <td><?= fmt_eur($t['fees_eur']) ?></td><td><?= $t['tx_type'] === 'SELL' ? fmt_eur($t['realized_pnl_eur']) : '—' ?></td></tr>
        <?php endforeach; ?></table>
    <?php endif; ?></div>
<?php endforeach; ?>
</div>
</body>
</html>
