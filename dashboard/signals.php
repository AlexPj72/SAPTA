<?php
require_once 'config.php';
require_once 'helpers.php';

$raw_signals = supabase_query('signals_raw', ['select' => '*', 'order' => 'timestamp.desc', 'limit' => 30]);
?>
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>SAPTA — Segnali grezzi</title>
    <link rel="icon" href="assets/favicon.svg">
    <link rel="stylesheet" href="assets/style.css">
</head>
<body>

<header class="hero compact">
    <div class="hero-top">
        <div>
            <div class="eyebrow">SAPTA v5.1.1</div>
            <h1>Segnali grezzi (Modulo B)</h1>
            <p>Output diretto dell'analisi, prima del filtro costi/rischio di Modulo E.</p>
        </div>
        <a class="back-link" href="index.php">← Dashboard</a>
    </div>
</header>

<?php render_nav('signals.php'); ?>

<div class="wrap">
<section>
    <div class="table-wrap">
    <table>
        <thead>
            <tr>
                <th>Quando</th><th>Ticker</th><th>Azione</th><th>Tipologia</th><th>Confidenza</th>
                <th>Prezzo</th><th>Invalidazione</th><th>Earnings</th><th>Barra</th>
            </tr>
        </thead>
        <tbody>
        <?php if (empty($raw_signals)): ?><tr><td colspan="9" class="empty-state">Nessun segnale disponibile.</td></tr><?php endif; ?>
        <?php foreach ($raw_signals as $s): ?>
        <tr>
            <td><?= e(date('d/m H:i', strtotime($s['timestamp']))) ?></td>
            <td><a class="ticker-link" href="grafico.php?ticker=<?= urlencode($s['ticker']) ?>"><?= e($s['ticker']) ?></a></td>
            <td><?= badge_azione($s['action']) ?></td>
            <td class="muted"><?= e($s['opportunity_type'] ?? '—') ?></td>
            <td><?= e($s['confidence_level'] ?? '—') ?><?php if (isset($s['confidence_multiplier'])): ?> <span class="muted">(x<?= number_format($s['confidence_multiplier'], 1) ?>)</span><?php endif; ?></td>
            <td><?= isset($s['close_price']) ? number_format($s['close_price'], 2) : '—' ?></td>
            <td>
                <?php if (isset($s['invalidation_price'])): ?>
                    <?= number_format($s['invalidation_price'], 2) ?>
                    <br><small class="muted"><?= e($s['invalidation_reason'] ?? '') ?></small>
                <?php else: ?>—<?php endif; ?>
            </td>
            <td><?= !empty($s['has_upcoming_earnings']) ? '<span class="badge warn">⚠️ sì</span>' : '<span class="muted">no</span>' ?></td>
            <td><?= !empty($s['is_provisional_bar']) ? '<span class="badge warn">provvisoria</span>' : '<span class="badge approved">definitiva</span>' ?></td>
        </tr>
        <?php endforeach; ?>
        </tbody>
    </table>
    </div>
</section>
</div>

<footer>SAPTA · Segnali grezzi · Pagina generata <?= date('d/m/Y H:i') ?></footer>
</body>
</html>
