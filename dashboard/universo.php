<?php
require_once 'config.php';

// Universo completo: non dipende dai segnali generati.
$universe = supabase_query('ticker_sectors', [
    'select' => 'ticker,sector',
    'order' => 'ticker.asc',
    'limit' => 500
]);

// Ultime barre giornaliere sufficienti per ricavare prezzo, variazione e mini-grafico.
$daily_rows = supabase_query('prezzi', [
    'select' => 'ticker,timestamp,close',
    'interval' => 'eq.1d',
    'order' => 'timestamp.desc',
    'limit' => 5000
]);

$by_ticker = [];
foreach ($daily_rows as $row) {
    $ticker = $row['ticker'] ?? '';
    if ($ticker === '' || !isset($row['close']) || $row['close'] === null) continue;
    if (!isset($by_ticker[$ticker])) $by_ticker[$ticker] = [];
    if (count($by_ticker[$ticker]) < 35) $by_ticker[$ticker][] = $row;
}

// Ultimi segnali: servono solo come informazione aggiuntiva, non per costruire l'universo.
$latest_signals = supabase_query('signals_filtered', [
    'select' => 'ticker,filtered_action,timestamp',
    'order' => 'timestamp.desc',
    'limit' => 200
]);
$signal_by_ticker = [];
foreach ($latest_signals as $s) {
    $t = $s['ticker'] ?? '';
    if ($t !== '' && !isset($signal_by_ticker[$t])) $signal_by_ticker[$t] = $s;
}

function e($value) {
    return htmlspecialchars((string)$value, ENT_QUOTES, 'UTF-8');
}

function sparkline_svg($rows) {
    if (count($rows) < 2) return '<span class="spark-empty">—</span>';
    $rows = array_reverse($rows);
    $values = array_map(fn($r) => (float)$r['close'], $rows);
    $min = min($values); $max = max($values);
    $range = ($max - $min) ?: 1;
    $w = 120; $h = 34; $pad = 2;
    $points = [];
    $n = count($values);
    foreach ($values as $i => $v) {
        $x = $pad + ($i / max(1, $n - 1)) * ($w - 2 * $pad);
        $y = $h - $pad - (($v - $min) / $range) * ($h - 2 * $pad);
        $points[] = round($x, 1) . ',' . round($y, 1);
    }
    $first = $values[0]; $last = $values[count($values)-1];
    $class = $last >= $first ? 'spark-up' : 'spark-down';
    return '<svg class="sparkline '.$class.'" viewBox="0 0 '.$w.' '.$h.'" role="img" aria-label="Andamento ultimi dati giornalieri"><polyline points="'.e(implode(' ', $points)).'" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
}

$rows = [];
foreach ($universe as $u) {
    $ticker = $u['ticker'] ?? '';
    $history = $by_ticker[$ticker] ?? [];
    $latest = $history[0] ?? null;
    $previous = $history[1] ?? null;
    $price = $latest['close'] ?? null;
    $change = null;
    if ($price !== null && $previous && (float)$previous['close'] != 0) {
        $change = ((float)$price / (float)$previous['close'] - 1) * 100;
    }
    $rows[] = [
        'ticker' => $ticker,
        'sector' => $u['sector'] ?? '—',
        'price' => $price,
        'change' => $change,
        'date' => $latest['timestamp'] ?? null,
        'history' => $history,
        'signal' => $signal_by_ticker[$ticker]['filtered_action'] ?? null
    ];
}

$filter = $_GET['filter'] ?? 'all';
$search = trim($_GET['q'] ?? '');
if ($filter === 'up') $rows = array_values(array_filter($rows, fn($r) => $r['change'] !== null && $r['change'] > 0));
if ($filter === 'down') $rows = array_values(array_filter($rows, fn($r) => $r['change'] !== null && $r['change'] < 0));
if ($filter === 'signals') $rows = array_values(array_filter($rows, fn($r) => $r['signal'] !== null));
if ($search !== '') {
    $rows = array_values(array_filter($rows, fn($r) => stripos($r['ticker'], $search) !== false || stripos($r['sector'], $search) !== false));
}

$sort = $_GET['sort'] ?? 'ticker';
usort($rows, function($a, $b) use ($sort) {
    if ($sort === 'change') return ($b['change'] ?? -INF) <=> ($a['change'] ?? -INF);
    if ($sort === 'price') return ($b['price'] ?? -INF) <=> ($a['price'] ?? -INF);
    return strcmp($a['ticker'], $b['ticker']);
});
?>
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>SAPTA — Universo</title>
    <link rel="stylesheet" href="assets/style.css">
</head>
<body>
<header class="hero compact">
    <div class="hero-top">
        <div>
            <div class="eyebrow">SAPTA v5.1.1</div>
            <h1>Universo titoli</h1>
            <p>Vista completa dell'universo monitorato, indipendente dalla generazione di segnali.</p>
        </div>
        <a class="back-link" href="index.php">← Dashboard</a>
    </div>
</header>

<nav class="nav-bar">
    <a href="index.php">Dashboard</a>
    <a class="active" href="universo.php">Universo <span><?= count($universe) ?></span></a>
    <a href="signals.php">Segnali</a>
    <a href="decisions.php">Paper Trading</a>
    <a href="capital.php">Capitale</a>
</nav>

<section class="toolbar-card">
    <div>
        <h2>Panoramica</h2>
        <p class="muted">Ogni ticker viene mostrato anche se non ha mai generato un segnale.</p>
    </div>
    <form method="get" class="universe-filters">
        <input type="search" name="q" value="<?= e($search) ?>" placeholder="Cerca ticker o settore…">
        <select name="filter">
            <option value="all" <?= $filter==='all'?'selected':'' ?>>Tutti</option>
            <option value="up" <?= $filter==='up'?'selected':'' ?>>In rialzo</option>
            <option value="down" <?= $filter==='down'?'selected':'' ?>>In ribasso</option>
            <option value="signals" <?= $filter==='signals'?'selected':'' ?>>Con segnale</option>
        </select>
        <select name="sort">
            <option value="ticker" <?= $sort==='ticker'?'selected':'' ?>>Ordina ticker</option>
            <option value="change" <?= $sort==='change'?'selected':'' ?>>Ordina variazione</option>
            <option value="price" <?= $sort==='price'?'selected':'' ?>>Ordina prezzo</option>
        </select>
        <button type="submit">Applica</button>
    </form>
</section>

<section class="universe-card">
    <div class="section-head">
        <div><h2><?= count($rows) ?> titoli visualizzati</h2><p class="muted">Ultimo close giornaliero disponibile</p></div>
        <div class="legend"><span class="dot up-dot"></span> rialzo <span class="dot down-dot"></span> ribasso</div>
    </div>
    <div class="table-wrap">
    <table class="universe-table">
        <thead><tr><th>Ticker</th><th>Settore</th><th>Ultimo prezzo</th><th>Giorno</th><th>Trend</th><th>Segnale</th><th></th></tr></thead>
        <tbody>
        <?php foreach ($rows as $r): ?>
            <tr>
                <td><a class="ticker-link" href="grafico.php?ticker=<?= urlencode($r['ticker']) ?>"><?= e($r['ticker']) ?></a></td>
                <td class="muted"><?= e($r['sector']) ?></td>
                <td><?= $r['price'] !== null ? number_format($r['price'], 2) : '—' ?></td>
                <td class="<?= ($r['change'] ?? 0) >= 0 ? 'positive' : 'negative' ?>">
                    <?= $r['change'] !== null ? (($r['change'] >= 0 ? '+' : '') . number_format($r['change'], 2) . '%') : '—' ?>
                </td>
                <td><?= sparkline_svg($r['history']) ?></td>
                <td><?php if ($r['signal']): ?><span class="badge signal-badge <?= strtolower(e($r['signal'])) ?>"><?= e($r['signal']) ?></span><?php else: ?><span class="muted">Nessuno</span><?php endif; ?></td>
                <td><a class="mini-button" href="grafico.php?ticker=<?= urlencode($r['ticker']) ?>">Apri grafico →</a></td>
            </tr>
        <?php endforeach; ?>
        <?php if (!$rows): ?><tr><td colspan="7" class="empty-state">Nessun titolo corrisponde ai filtri.</td></tr><?php endif; ?>
        </tbody>
    </table>
    </div>
</section>

<footer>SAPTA · Universo monitorato: <?= count($universe) ?> ticker · Pagina generata <?= date('d/m/Y H:i') ?></footer>
</body>
</html>
