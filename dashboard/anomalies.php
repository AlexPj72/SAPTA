<?php
require_once 'config.php';
require_once 'helpers.php';

$candidates = supabase_query('screening_candidates', ['select' => '*', 'order' => 'timestamp.desc', 'limit' => 30]);
?>
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>SAPTA — Radar anomalie</title>
    <link rel="stylesheet" href="assets/style.css">
</head>
<body>

<header class="hero compact">
    <div class="hero-top">
        <div>
            <div class="eyebrow">SAPTA v5.1.1</div>
            <h1>Radar anomalie (Modulo H, H1/H2)</h1>
            <p>Screening leggero su tutto l'universo prima dell'analisi completa.</p>
        </div>
        <a class="back-link" href="index.php">← Dashboard</a>
    </div>
</header>

<?php render_nav('anomalies.php'); ?>

<div class="wrap">
<section>
    <div class="table-wrap">
    <table>
        <thead>
            <tr>
                <th>Quando</th><th>Ticker</th><th>Stato</th><th>H1</th><th>Anomaly</th>
                <th>Contesto</th><th>Liquidità</th><th>Qualità dato</th><th>News</th>
            </tr>
        </thead>
        <tbody>
        <?php if (empty($candidates)): ?>
        <tr><td colspan="9" class="empty-state">Nessun candidato disponibile — normale a mercato chiuso o con storico intraday ancora scarso.</td></tr>
        <?php endif; ?>
        <?php foreach ($candidates as $c): ?>
        <tr>
            <td><?= e(date('d/m H:i', strtotime($c['timestamp']))) ?></td>
            <td><a class="ticker-link" href="grafico.php?ticker=<?= urlencode($c['ticker']) ?>"><?= e($c['ticker']) ?></a></td>
            <td><span class="badge <?= $c['status'] === 'promosso_a_B' ? 'approved' : ($c['status'] === 'scartato_h2' ? 'rejected' : 'hold') ?>"><?= e($c['status'] ?? '') ?></span></td>
            <td><?= isset($c['h1_score']) ? number_format($c['h1_score'], 2) : '—' ?></td>
            <td><?= isset($c['anomaly_score']) ? number_format($c['anomaly_score'], 2) : '—' ?></td>
            <td><?= isset($c['context_score']) ? number_format($c['context_score'], 2) : '—' ?></td>
            <td class="muted"><?= e($c['liquidity_bucket'] ?? '—') ?></td>
            <td><?= e($c['data_quality_flag'] ?? '—') ?></td>
            <td><?= isset($c['news_light_count']) ? (int) $c['news_light_count'] : '—' ?></td>
        </tr>
        <?php endforeach; ?>
        </tbody>
    </table>
    </div>
</section>
</div>

<footer>SAPTA · Radar anomalie · Pagina generata <?= date('d/m/Y H:i') ?></footer>
</body>
</html>
