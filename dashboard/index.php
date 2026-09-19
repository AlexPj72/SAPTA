<?php
require_once 'config.php';
require_once 'helpers.php';

// Ultimi segnali filtrati (Modulo E) — include ora Sezione 15/16 (rischio + ranking)
$signals = supabase_query('signals_filtered', [
    'select' => '*',
    'order' => 'timestamp.desc',
    'limit' => 25
]);

// Candidati screening recenti (Modulo H v5.1.1)
$candidates = supabase_query('screening_candidates', [
    'select' => '*',
    'order' => 'timestamp.desc',
    'limit' => 15
]);
// Mappa per id, per collegare i segnali ai punteggi H2 originali (spiegazione)
$candidates_by_id = [];
foreach ($candidates as $c) { $candidates_by_id[$c['id']] = $c; }
// Se un segnale in tabella referenzia un candidato non tra gli ultimi 15, lo recuperiamo a parte
$missing_ids = [];
foreach ($signals as $s) {
    $cid = $s['screening_candidate_id'] ?? null;
}

// Capitale corrente
$capital_history = supabase_query('capital_state', [
    'select' => 'capital_eur,created_at',
    'order' => 'created_at.desc',
    'limit' => 1
]);
$current_capital = $capital_history[0]['capital_eur'] ?? null;

// KPI
$n_buy_sell = 0; $max_exposure = 0.0; $last_ts = null;
foreach ($signals as $s) {
    if (($s['filtered_action'] ?? 'HOLD') !== 'HOLD' && !empty($s['filter_passed'])) $n_buy_sell++;
    if (isset($s['portfolio_exposure_pct'])) $max_exposure = max($max_exposure, (float) $s['portfolio_exposure_pct']);
    if (!$last_ts && isset($s['timestamp'])) $last_ts = $s['timestamp'];
}
$n_candidates_today = count($candidates);
?>
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>SAPTA — Dashboard</title>
    <link rel="stylesheet" href="assets/style.css">
</head>
<body>

<header class="hero">
    <div class="hero-top">
        <div>
            <div class="eyebrow">SAPTA v5.1.1</div>
            <h1>Dashboard operativa</h1>
            <p>Panoramica di segnali, candidati e capitale. Aggiornata ad ogni ricarica pagina.</p>
        </div>
        <div style="display:flex; gap:10px; flex-wrap:wrap;">
            <a class="back-link" href="briefing.php">📋 Briefing di oggi</a>
            <a class="back-link" href="decisions.php">📝 Paper trading guidato →</a>
        </div>
    </div>
</header>

<div class="stat-grid">
    <div class="stat-card">
        <div class="stat-label">Capitale corrente</div>
        <div class="stat-value"><?= $current_capital !== null ? fmt_eur($current_capital) : '—' ?></div>
        <div class="stat-sub"><a href="capital.php">gestisci →</a></div>
    </div>
    <div class="stat-card <?= $n_buy_sell > 0 ? 'good' : '' ?>">
        <div class="stat-label">Opportunità attive</div>
        <div class="stat-value"><?= $n_buy_sell ?></div>
        <div class="stat-sub">BUY/SELL approvati (ultimi 25 segnali)</div>
    </div>
    <div class="stat-card <?= $max_exposure > 0.5 ? 'warn' : '' ?>">
        <div class="stat-label">Esposizione stimata</div>
        <div class="stat-value"><?= $max_exposure > 0 ? number_format($max_exposure * 100, 0) . '%' : '—' ?></div>
        <div class="stat-sub">del capitale, se eseguite insieme</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">Candidati screening</div>
        <div class="stat-value"><?= $n_candidates_today ?></div>
        <div class="stat-sub"><a href="anomalies.php">vedi radar →</a></div>
    </div>
</div>

<?php render_nav('index.php'); ?>

<div class="wrap">

<section>
    <div class="section-head">
        <div>
            <h2>Segnali filtrati (ultimi 25)</h2>
            <p class="muted">Output di Modulo E — rendimento netto, rischio di portafoglio e score di ranking già applicati.</p>
        </div>
    </div>
    <div class="table-wrap">
    <table>
        <thead>
            <tr>
                <th>Quando</th>
                <th>Ticker</th>
                <th>Azione</th>
                <th>Score</th>
                <th>Rend. netto</th>
                <th>Target / Stop</th>
                <th>Stato</th>
                <th>Spiegazione</th>
            </tr>
        </thead>
        <tbody>
            <?php if (empty($signals)): ?>
            <tr><td colspan="8" class="empty-state">Nessun segnale disponibile al momento.</td></tr>
            <?php endif; ?>
            <?php foreach ($signals as $s): ?>
            <?php $cand = $candidates_by_id[$s['screening_candidate_id'] ?? null] ?? null; ?>
            <tr>
                <td><?= e(date('d/m H:i', strtotime($s['timestamp']))) ?></td>
                <td><a class="ticker-link" href="grafico.php?ticker=<?= urlencode($s['ticker']) ?>"><?= e($s['ticker']) ?></a></td>
                <td><?= badge_azione($s['filtered_action'] ?? 'HOLD') ?></td>
                <td><?= rank_pill($s['final_rank_score'] ?? null) ?></td>
                <td class="<?= (($s['expected_net_return'] ?? 0) >= 0) ? 'positive' : 'negative' ?>">
                    <?= fmt_pct($s['expected_net_return'] ?? null) ?>
                </td>
                <td>
                    <?= isset($s['target_price']) ? '🎯 ' . fmt_eur($s['target_price']) : '—' ?><br>
                    <?= isset($s['invalidation_price']) ? '🛑 ' . fmt_eur($s['invalidation_price']) : '' ?>
                </td>
                <td>
                    <?php if (($s['filtered_action'] ?? 'HOLD') === 'HOLD' && ($s['original_action'] ?? '') === 'HOLD'): ?>
                        <span class="badge hold">nessuna azione</span>
                    <?php elseif (!empty($s['filter_passed'])): ?>
                        <span class="badge approved">✅ approvato</span>
                        <br><a class="mini-button" href="decisions.php?ticker=<?= urlencode($s['ticker']) ?>&signal_id=<?= (int) $s['id'] ?>">registra →</a>
                    <?php else: ?>
                        <span class="badge rejected">❌ declassato</span>
                    <?php endif; ?>
                </td>
                <td>
                    <details>
                        <summary class="explain-toggle">perché?</summary>
                        <div class="explain"><?= spiega_segnale($s, $cand) ?></div>
                    </details>
                </td>
            </tr>
            <?php endforeach; ?>
        </tbody>
    </table>
    </div>
</section>

<section>
    <div class="section-head">
        <div>
            <h2>Ipotesi IA di oggi (osservazione, sotto soglia H1)</h2>
            <p class="muted">👀 Solo watch — non sono segnali operativi. Se un titolo ha già un segnale reale attivo, lo vedi in colonna "Segnale".</p>
        </div>
    </div>
    <?php
    $hypotheses = supabase_query('ai_hypotheses', ['select' => '*', 'hypothesis_date' => 'eq.' . date('Y-m-d'), 'order' => 'created_at.desc']);
    $tipo_label = ['volume' => 'Volume↑, aspetta prezzo', 'prezzo' => 'Prezzo↑, aspetta volume', 'debole' => 'Segnale debole'];
    ?>
    <?php if (empty($hypotheses)): ?>
        <p class="empty-state">Nessuna ipotesi oggi finora.</p>
    <?php else: ?>
    <div class="table-wrap">
    <table>
        <thead><tr><th>Ora</th><th>Ticker</th><th>Tipo</th><th>Stato</th><th>Livello</th><th>Motivazione</th><th>Var.</th><th>Volume</th><th>Segnale</th><th>Alert</th></tr></thead>
        <tbody>
        <?php foreach ($hypotheses as $h): ?>
        <tr>
            <td><?= e(date('H:i', strtotime($h['created_at']))) ?></td>
            <td><a class="ticker-link" href="grafico.php?ticker=<?= urlencode($h['ticker']) ?>"><?= e($h['ticker']) ?></a></td>
            <td class="muted"><?= e($tipo_label[$h['tipo_anomalia'] ?? ''] ?? '—') ?></td>
            <td>
                <?php $st = $h['status'] ?? 'in_osservazione'; $st_map = [
                    'confermato' => ['✅ confermato', 'approved'], 'invalidato' => ['❌ invalidato', 'rejected'],
                    'scaduto' => ['⏱ scaduto', 'hold'], 'in_osservazione' => ['👀 in osservazione', 'warn'],
                ]; [$st_txt, $st_cls] = $st_map[$st] ?? $st_map['in_osservazione']; ?>
                <span class="badge <?= $st_cls ?>"><?= e($st_txt) ?></span>
            </td>
            <td><span class="badge <?= $h['livello'] === 'alto' ? 'warn' : 'hold' ?>"><?= e($h['livello']) ?></span></td>
            <td style="white-space:normal; max-width:340px;"><?= e($h['motivazione']) ?></td>
            <td class="<?= ($h['price_change_pct'] ?? 0) >= 0 ? 'positive' : 'negative' ?>"><?= number_format($h['price_change_pct'], 2) ?>%</td>
            <td><?= number_format($h['volume_ratio'], 1) ?>x</td>
            <td><?php if (!empty($h['has_active_signal'])): ?>
                <span class="badge approved">🟢 <?= e($h['linked_action']) ?></span>
                <br><small class="muted">T <?= number_format($h['linked_target_price'] ?? 0, 2) ?> / I <?= number_format($h['linked_invalidation_price'] ?? 0, 2) ?></small>
            <?php else: ?><span class="muted">nessuno</span><?php endif; ?></td>
            <td><?= (!empty($h['alerted_telegram']) ? '📱' : '') . (!empty($h['alerted_email']) ? '✉️' : '') ?: '—' ?></td>
        </tr>
        <?php endforeach; ?>
        </tbody>
    </table>

    </div>
    <?php endif; ?>
</section>

<section>
    <div class="section-head">
        <div>
            <h2>Candidati screening (Modulo H, ultimi 15)</h2>
            <p class="muted">Anomalie rilevate da H1/H2, prima ancora di arrivare all'analisi di Modulo B.</p>
        </div>
        <a class="mini-button" href="anomalies.php">vedi tutto il radar →</a>
    </div>
    <div class="table-wrap">
    <table>
        <thead>
            <tr>
                <th>Quando</th><th>Ticker</th><th>Stato</th><th>Liquidità</th><th>News</th><th>Contesto</th>
            </tr>
        </thead>
        <tbody>
            <?php if (empty($candidates)): ?>
            <tr><td colspan="6" class="empty-state">Nessun candidato al momento — normale a mercato chiuso o con storico intraday ancora scarso.</td></tr>
            <?php endif; ?>
            <?php foreach ($candidates as $c): ?>
            <tr>
                <td><?= e(date('d/m H:i', strtotime($c['timestamp']))) ?></td>
                <td><a class="ticker-link" href="grafico.php?ticker=<?= urlencode($c['ticker']) ?>"><?= e($c['ticker']) ?></a></td>
                <td><?= e($c['status'] ?? '') ?></td>
                <td><?= e($c['liquidity_bucket'] ?? '—') ?></td>
                <td><?= isset($c['news_light_count']) ? (int) $c['news_light_count'] : '—' ?></td>
                <td><?= isset($c['context_score']) ? number_format($c['context_score'], 2) : '—' ?></td>
            </tr>
            <?php endforeach; ?>
        </tbody>
    </table>
    </div>
</section>

</div>

<footer>SAPTA · Pagina generata <?= date('d/m/Y H:i') ?></footer>
</body>
</html>
