<?php
require_once 'config.php';
require_once 'helpers.php';

$today = date('Y-m-d');

// Segnali operativi reali (Modulo E) di oggi, approvati e non HOLD
$real_signals = supabase_query('signals_filtered', [
    'select' => '*',
    'filter_passed' => 'eq.true',
    'filtered_action' => 'neq.HOLD',
    'timestamp' => 'gte.' . $today . 'T00:00:00',
    'order' => 'timestamp.desc',
]);

// Ipotesi AI Watch appena confermate oggi (persistenza verificata, vedi ciclo di conferma)
$confirmed_hyp = supabase_query('ai_hypotheses', [
    'select' => '*',
    'hypothesis_date' => 'eq.' . $today,
    'status' => 'eq.confermato',
    'order' => 'resolved_at.desc',
]);

// Unifica in una sola lista, ordinata per orario più recente
$items = [];
foreach ($real_signals as $s) {
    $items[] = [
        'kind' => 'segnale', 'ticker' => $s['ticker'], 'ts' => $s['timestamp'],
        'action' => $s['filtered_action'], 'score' => $s['final_rank_score'] ?? null,
        'summary' => spiega_segnale($s, null), 'raw' => $s,
    ];
}
foreach ($confirmed_hyp as $h) {
    $items[] = [
        'kind' => 'ipotesi', 'ticker' => $h['ticker'], 'ts' => $h['resolved_at'] ?? $h['created_at'],
        'action' => null, 'score' => null,
        'summary' => e($h['motivazione']) . " (confermato dopo " . plural_it((int) ($h['checked_count'] ?? 0), 'ricontrollo', 'ricontrolli') . ")",
        'raw' => $h,
    ];
}
usort($items, fn($a, $b) => strtotime($b['ts']) <=> strtotime($a['ts']));

// [NUOVO 19/09 - Punto 4] Contesto di mercato generale
$market = get_market_direction_dashboard();
?>
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="refresh" content="900">
    <title>SAPTA — Da valutare oggi</title>
    <link rel="icon" href="assets/favicon.svg">
    <link rel="stylesheet" href="assets/style.css">
</head>
<body>

<header class="hero">
    <div class="hero-top">
        <div>
            <div class="eyebrow">SAPTA v5.1.1</div>
            <h1>Da valutare oggi</h1>
            <p>Tutto quello che merita la tua attenzione adesso, in un unico posto — segnali operativi reali e ipotesi qualitative confermate. Nient'altro.</p>
        </div>
        <a class="back-link" href="index.php">← Dashboard completa</a>
    </div>
</header>

<?php render_nav('today.php'); ?>

<div class="wrap">

<section style="padding: 12px 24px;">
    <span class="legend">📊 Contesto di mercato oggi — <?= market_direction_badge($market['usa'], 'S&amp;P 500 (USA)') ?> · <?= market_direction_badge($market['italia'], 'FTSE MIB (Italia)') ?></span>
</section>

<section>
    <div class="section-head">
        <div><h2><?= count($items) ?> elementi da valutare</h2><p class="muted">Si aggiorna da solo ogni 15 minuti.</p></div>
    </div>

    <?php if (empty($items)): ?>
        <p class="empty-state">Niente da valutare al momento — nessun segnale operativo e nessuna ipotesi confermata oggi. Torna più tardi o guarda il <a href="briefing.php">briefing di stamattina</a>.</p>
    <?php else: ?>
    <ul class="step-list">
        <?php foreach ($items as $it): ?>
        <li>
            <div class="step-num" style="background: <?= $it['kind'] === 'segnale' ? 'var(--brand)' : '#ea580c' ?>;">
                <?= $it['kind'] === 'segnale' ? '🎯' : '✅' ?>
            </div>
            <div class="step-body" style="flex:1;">
                <b>
                    <?= market_flag($it['ticker']) ?> <?= e($it['ticker']) ?>
                    <?php if ($it['action']): ?> · <?= badge_azione($it['action']) ?><?php endif; ?>
                    <?php if ($it['score'] !== null): ?> · <?= rank_pill($it['score']) ?><?php endif; ?>
                    <span class="badge <?= $it['kind'] === 'segnale' ? 'approved' : 'warn' ?>" style="margin-left:6px;">
                        <?= $it['kind'] === 'segnale' ? 'segnale operativo' : 'ipotesi confermata' ?>
                    </span>
                </b>
                <span style="display:block; margin: 4px 0 8px;"><?= $it['summary'] ?></span>
                <span class="muted" style="font-size:12px;"><?= e(date('H:i', strtotime($it['ts']))) ?></span>
            </div>
            <div style="flex:none; align-self:center;">
                <a class="btn" href="valuta.php?ticker=<?= urlencode($it['ticker']) ?>&kind=<?= $it['kind'] ?>&id=<?= (int) ($it['raw']['id'] ?? 0) ?>">Valuta →</a>
            </div>
        </li>
        <?php endforeach; ?>
    </ul>
    <?php endif; ?>
</section>

</div>

<footer>SAPTA · Da valutare oggi · Pagina generata <?= date('d/m/Y H:i') ?></footer>
</body>
</html>
