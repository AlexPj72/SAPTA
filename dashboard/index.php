<?php
require_once 'config.php';

$signals = supabase_query('signals_filtered', [
    'select' => '*', 'order' => 'timestamp.desc', 'limit' => 20
]);
$candidates = supabase_query('screening_candidates', [
    'select' => '*', 'order' => 'timestamp.desc', 'limit' => 15
]);
$capital_history = supabase_query('capital_state', [
    'select' => 'capital_eur,created_at', 'order' => 'created_at.desc', 'limit' => 1
]);
$current_capital = $capital_history[0]['capital_eur'] ?? null;

$universe = supabase_query('ticker_sectors', ['select' => 'ticker', 'limit' => 500]);
$universe_count = count($universe);
$approved_count = 0;
$signal_count = count($signals);
foreach ($signals as $s) if (!empty($s['filter_passed'])) $approved_count++;
?>
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>SAPTA v5.1.1 — Dashboard</title>
    <link rel="stylesheet" href="assets/style.css">
</head>
<body>
<header class="hero">
    <div class="hero-top">
        <div>
            <div class="eyebrow">SYSTEM OVERVIEW · v5.1.1</div>
            <h1>SAPTA <span>Trading Intelligence</span></h1>
            <p>Monitoraggio, analisi e paper trading in un'unica dashboard.</p>
        </div>
        <div class="status-pill"><span class="status-dot"></span> Sistema online</div>
    </div>
    <div class="hero-meta">
        <span>Ultimo aggiornamento: <?= date('d/m/Y H:i') ?></span>
        <span>Capitale: <strong><?= $current_capital !== null ? '€' . number_format($current_capital, 2) : 'Non impostato' ?></strong></span>
    </div>
</header>

<nav class="nav-bar">
    <a class="active" href="index.php">Dashboard</a>
    <a href="universo.php">Universo <span><?= $universe_count ?></span></a>
    <a href="signals.php">Segnali</a>
    <a href="decisions.php">Paper Trading</a>
    <a href="capital.php">Capitale</a>
</nav>

<section class="kpi-grid">
    <a class="kpi-card accent" href="universo.php"><div class="kpi-label">UNIVERSO</div><div class="kpi-value"><?= $universe_count ?></div><div class="kpi-sub">titoli monitorati <span>→</span></div></a>
    <a class="kpi-card" href="signals.php"><div class="kpi-label">SEGNALI</div><div class="kpi-value"><?= $signal_count ?></div><div class="kpi-sub">ultimi segnali filtrati <span>→</span></div></a>
    <a class="kpi-card" href="decisions.php"><div class="kpi-label">APPROVATI</div><div class="kpi-value"><?= $approved_count ?></div><div class="kpi-sub">pronti per decisione <span>→</span></div></a>
    <a class="kpi-card" href="capital.php"><div class="kpi-label">CAPITALE</div><div class="kpi-value small-value"><?= $current_capital !== null ? '€' . number_format($current_capital, 0, ',', '.') : '—' ?></div><div class="kpi-sub">capitale corrente <span>→</span></div></a>
</section>

<section class="quick-links">
    <div><h2>Centro operativo</h2><p class="muted">Accesso rapido alle aree principali di SAPTA.</p></div>
    <div class="quick-grid">
        <a href="universo.php" class="quick-card"><span class="quick-icon">◈</span><div><strong>Universo titoli</strong><small>Tutti i <?= $universe_count ?> ticker con andamento giornaliero</small></div><b>→</b></a>
        <a href="signals.php" class="quick-card"><span class="quick-icon">↗</span><div><strong>Segnali dettagliati</strong><small>Analisi del Modulo B e indicatori</small></div><b>→</b></a>
        <a href="decisions.php" class="quick-card"><span class="quick-icon">◎</span><div><strong>Paper trading</strong><small>Decisioni e operazioni virtuali</small></div><b>→</b></a>
        <a href="capital.php" class="quick-card"><span class="quick-icon">€</span><div><strong>Gestione capitale</strong><small>Capitale di riferimento del sistema</small></div><b>→</b></a>
    </div>
</section>

<section>
    <div class="section-head"><div><h2>Segnali filtrati</h2><p class="muted">Ultimi 20 · Modulo E</p></div><a class="section-link" href="signals.php">Vedi tutti →</a></div>
    <div class="table-wrap"><table>
        <thead><tr><th>Timestamp</th><th>Ticker</th><th>Azione</th><th>Attesa netta</th><th>Target / Invalidation</th><th>Stato</th></tr></thead>
        <tbody>
        <?php if (empty($signals)): ?><tr><td colspan="6" class="empty-state">Nessun segnale disponibile.</td></tr><?php endif; ?>
        <?php foreach ($signals as $s): ?>
        <tr>
            <td class="muted"><?= date('d/m H:i', strtotime($s['timestamp'])) ?></td>
            <td><a class="ticker-link" href="grafico.php?ticker=<?= urlencode($s['ticker']) ?>"><?= htmlspecialchars($s['ticker']) ?></a></td>
            <td><span class="action-chip <?= strtolower($s['filtered_action']) ?>"><?= htmlspecialchars($s['filtered_action']) ?></span></td>
            <td><?= number_format(($s['expected_net_return'] ?? 0) * 100, 2) ?>%</td>
            <td><?= isset($s['target_price']) ? '🎯 ' . number_format($s['target_price'], 2) : '—' ?> / <?= isset($s['invalidation_price']) ? '🛑 ' . number_format($s['invalidation_price'], 2) : '—' ?></td>
            <td><?php if (!empty($s['filter_passed'])): ?><span class="badge approved">APPROVATO</span><?php elseif ($s['filtered_action'] === 'HOLD'): ?><span class="badge hold">HOLD</span><?php else: ?><span class="badge rejected">DECLASSATO</span><?php endif; ?></td>
        </tr>
        <?php endforeach; ?>
        </tbody>
    </table></div>
</section>

<section>
    <div class="section-head"><div><h2>Screening</h2><p class="muted">Ultimi candidati · Modulo H</p></div></div>
    <div class="table-wrap"><table>
        <thead><tr><th>Timestamp</th><th>Ticker</th><th>Status</th><th>Liquidità</th><th>News</th><th>Context</th></tr></thead>
        <tbody>
        <?php if (empty($candidates)): ?><tr><td colspan="6" class="empty-state">Nessun candidato disponibile. È normale a mercato chiuso.</td></tr><?php endif; ?>
        <?php foreach ($candidates as $c): ?>
        <tr><td class="muted"><?= date('d/m H:i', strtotime($c['timestamp'])) ?></td><td><strong><?= htmlspecialchars($c['ticker']) ?></strong></td><td><?= htmlspecialchars($c['status'] ?? '') ?></td><td><?= htmlspecialchars($c['liquidity_bucket'] ?? '') ?></td><td><?= isset($c['news_light_count']) ? (int)$c['news_light_count'] : '—' ?></td><td><?= isset($c['context_score']) ? number_format($c['context_score'], 2) : '—' ?></td></tr>
        <?php endforeach; ?>
        </tbody>
    </table></div>
</section>

<footer>SAPTA v5.1.1 · Dashboard principale · <a href="capital.php">Gestisci capitale</a></footer>
</body>
</html>
