<?php
require_once 'config.php';
require_once 'helpers.php';

$ticker = $_GET['ticker'] ?? '';
if ($ticker === '') {
    die('Ticker mancante. <a href="index.php">Torna alla dashboard</a>');
}

// Storico giornaliero (ultimi 120gg)
$daily = supabase_query('prezzi', [
    'select' => 'timestamp,close,volume',
    'ticker' => 'eq.' . $ticker,
    'interval' => 'eq.1d',
    'order' => 'timestamp.desc',
    'limit' => 120
]);
$daily = array_reverse($daily);

// Intraday 15m: fetch unico e ampio, riusato sia per la sessione corrente
// (grafico intraday) sia per il trend settimanale (ultimi 5 giorni con dati).
$intraday_raw = supabase_query('prezzi', [
    'select' => 'timestamp,close,volume',
    'ticker' => 'eq.' . $ticker,
    'interval' => 'eq.15m',
    'order' => 'timestamp.desc',
    'limit' => 600
]);
$last_session_date = !empty($intraday_raw) ? substr($intraday_raw[0]['timestamp'], 0, 10) : null;
$intraday = array_values(array_filter($intraday_raw, fn($r) => substr($r['timestamp'], 0, 10) === $last_session_date));
$intraday = array_reverse($intraday);

// Trend settimanale: ultimi 5 giorni di mercato con dati intraday disponibili
// (non ultimi 7 giorni di calendario, per non contare weekend a vuoto)
$distinct_dates = array_values(array_unique(array_map(fn($r) => substr($r['timestamp'], 0, 10), $intraday_raw)));
sort($distinct_dates);
$weekly_dates = array_slice($distinct_dates, -5);
$weekly = array_values(array_filter($intraday_raw, fn($r) => in_array(substr($r['timestamp'], 0, 10), $weekly_dates, true)));
$weekly = array_reverse($weekly);

// Trend mensile: ultimi 30 giorni di trading dallo storico giornaliero
$monthly = array_slice($daily, -30);

// Ultimo segnale filtrato per questo ticker + il candidato H2 collegato, per la spiegazione
$last_signal_rows = supabase_query('signals_filtered', [
    'select' => '*',
    'ticker' => 'eq.' . $ticker,
    'order' => 'timestamp.desc',
    'limit' => 1
]);
$last_signal = $last_signal_rows[0] ?? null;
$last_candidate = null;
if ($last_signal && !empty($last_signal['screening_candidate_id'])) {
    $rows = supabase_query('screening_candidates', [
        'select' => '*', 'id' => 'eq.' . $last_signal['screening_candidate_id'], 'limit' => 1
    ]);
    $last_candidate = $rows[0] ?? null;
}
$target_price = $last_signal['target_price'] ?? null;
$invalidation_price = $last_signal['invalidation_price'] ?? null;

// Statistiche rapide
$last_close = !empty($daily) ? (float) end($daily)['close'] : null;
$prev_close = count($daily) > 1 ? (float) $daily[count($daily) - 2]['close'] : null;
$change_pct = ($last_close !== null && $prev_close) ? (($last_close / $prev_close - 1) * 100) : null;
$closes_120 = array_map(fn($d) => (float) $d['close'], $daily);
$min_120 = $closes_120 ? min($closes_120) : null;
$max_120 = $closes_120 ? max($closes_120) : null;

$daily_labels = array_map(fn($d) => date('d/m/y', strtotime($d['timestamp'])), $daily);
$daily_values = array_map(fn($d) => (float) $d['close'], $daily);
$monthly_labels = array_map(fn($d) => date('d/m', strtotime($d['timestamp'])), $monthly);
$monthly_values = array_map(fn($d) => (float) $d['close'], $monthly);
$weekly_labels = array_map(fn($d) => date('d/m H:i', strtotime($d['timestamp'])), $weekly);
$weekly_values = array_map(fn($d) => (float) $d['close'], $weekly);
$intraday_labels = array_map(fn($d) => date('H:i', strtotime($d['timestamp'])), $intraday);
$intraday_values = array_map(fn($d) => (float) $d['close'], $intraday);
$market = market_status($ticker);
?>
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="refresh" content="900">
    <title>SAPTA — <?= e($ticker) ?></title>
    <link rel="icon" href="assets/favicon.svg">
    <link rel="stylesheet" href="assets/style.css">
    <script src="assets/chart.umd.min.js"></script>
    <script src="assets/charts.js"></script>
</head>
<body>

<header class="hero compact">
    <div class="hero-top">
        <div>
            <div class="eyebrow">SAPTA v5.1.1</div>
            <h1><?= market_flag($ticker) ?> <?= e($ticker) ?><?php if ($change_pct !== null): ?>
                <span style="font-size:16px; font-weight:700; opacity:.9;">
                    <?= $change_pct >= 0 ? '▲' : '▼' ?> <?= number_format(abs($change_pct), 2) ?>%
                </span>
            <?php endif; ?></h1>
            <p><?= $last_close !== null ? 'Ultimo close: ' . fmt_eur($last_close) : 'Nessuno storico disponibile' ?>
                · <span class="badge <?= $market['aperto'] ? 'approved' : 'hold' ?>"><?= $market['aperto'] ? '🟢' : '⚪' ?> <?= e($market['label']) ?></span>
            </p>
        </div>
        <a class="back-link" href="index.php">← Dashboard</a>
    </div>
</header>

<div class="stat-grid">
    <div class="stat-card">
        <div class="stat-label">Ultimo close</div>
        <div class="stat-value"><?= fmt_eur($last_close) ?></div>
    </div>
    <div class="stat-card <?= ($change_pct ?? 0) >= 0 ? 'good' : 'bad' ?>">
        <div class="stat-label">Variazione gg.</div>
        <div class="stat-value"><?= $change_pct !== null ? (($change_pct >= 0 ? '+' : '') . number_format($change_pct, 2) . '%') : '—' ?></div>
    </div>
    <div class="stat-card">
        <div class="stat-label">Min / Max 120gg</div>
        <div class="stat-value" style="font-size:16px;"><?= $min_120 !== null ? fmt_eur($min_120, 1) . ' – ' . fmt_eur($max_120, 1) : '—' ?></div>
    </div>
    <div class="stat-card">
        <div class="stat-label">Ultimo segnale</div>
        <div class="stat-value" style="font-size:16px;"><?= $last_signal ? badge_azione($last_signal['filtered_action'] ?? 'HOLD') : '—' ?></div>
    </div>
</div>

<?php render_nav(''); ?>

<div class="wrap">

<?php if ($last_signal): ?>
<section>
    <h2>Perché questo segnale</h2>
    <div class="explain" style="max-width:none;"><?= spiega_segnale($last_signal, $last_candidate) ?></div>
</section>
<?php endif; ?>

<section class="chart-card">
    <div class="section-head">
        <div><h2>Storico giornaliero</h2><p class="muted">Ultimi <?= count($daily) ?> giorni di trading</p></div>
    </div>
    <?php if (empty($daily)): ?>
        <p class="muted">Nessuno storico giornaliero disponibile per questo ticker.</p>
    <?php else: ?>
        <div class="chart-wrap">
            <canvas id="dailyChart"></canvas>
        </div>
        <div id="dailyChartError" class="chart-error" style="display:none; margin-top:10px;">⚠️ Il grafico non si è caricato (Chart.js non disponibile). Prova a ricaricare la pagina; se il problema resta, segnalalo.</div>
        <div class="chart-legend-row">
            <span><i style="background:#4f46e5"></i> Prezzo di chiusura</span>
            <?php if ($target_price): ?><span><i style="background:#16a34a"></i> Target €<?= number_format($target_price, 2) ?></span><?php endif; ?>
            <?php if ($invalidation_price): ?><span><i style="background:#dc2626"></i> Invalidazione €<?= number_format($invalidation_price, 2) ?></span><?php endif; ?>
        </div>
    <?php endif; ?>
</section>

<section class="chart-card">
    <div class="section-head">
        <div><h2>Trend ultimo mese</h2><p class="muted">Ultimi <?= count($monthly) ?> giorni di trading</p></div>
    </div>
    <?php if (empty($monthly)): ?>
        <p class="muted">Nessuno storico disponibile per questo periodo.</p>
    <?php else: ?>
        <div class="chart-wrap">
            <canvas id="monthlyChart"></canvas>
        </div>
        <div id="monthlyChartError" class="chart-error" style="display:none; margin-top:10px;">⚠️ Il grafico non si è caricato (Chart.js non disponibile). Prova a ricaricare la pagina; se il problema resta, segnalalo.</div>
        <div class="chart-legend-row"><span><i style="background:#0891b2"></i> Prezzo di chiusura</span></div>
    <?php endif; ?>
</section>

<section class="chart-card">
    <div class="section-head">
        <div><h2>Trend ultima settimana</h2><p class="muted"><?= !empty($weekly_dates) ? count($weekly_dates) . ' giorni di mercato, dettaglio ogni 15 min' : 'Nessun dato' ?></p></div>
    </div>
    <?php if (empty($weekly)): ?>
        <p class="muted">Nessun dato intraday sufficiente per la settimana (lo storico a 15 minuti è ancora in accumulo).</p>
    <?php else: ?>
        <div class="chart-wrap">
            <canvas id="weeklyChart"></canvas>
        </div>
        <div id="weeklyChartError" class="chart-error" style="display:none; margin-top:10px;">⚠️ Il grafico non si è caricato (Chart.js non disponibile). Prova a ricaricare la pagina; se il problema resta, segnalalo.</div>
        <div class="chart-legend-row"><span><i style="background:#ea580c"></i> Prezzo di chiusura (15m)</span></div>
    <?php endif; ?>
</section>

<section class="chart-card">
    <div class="section-head">
        <div><h2>Intraday 15 minuti</h2><p class="muted"><?= $last_session_date ? 'Sessione del ' . e(date('d/m/Y', strtotime($last_session_date))) . ' — ' . count($intraday) . ' barre, si aggiorna da solo ogni 15 min' : 'Nessun dato' ?></p></div>
    </div>
    <?php if (empty($intraday)): ?>
        <p class="muted">Nessun dato intraday disponibile per questo ticker.</p>
    <?php else: ?>
        <div class="chart-wrap">
            <canvas id="intradayChart"></canvas>
        </div>
        <div id="intradayChartError" class="chart-error" style="display:none; margin-top:10px;">⚠️ Il grafico non si è caricato (Chart.js non disponibile). Prova a ricaricare la pagina; se il problema resta, segnalalo.</div>
        <div class="chart-legend-row">
            <span><i style="background:#7c3aed"></i> Prezzo di chiusura (15m)</span>
        </div>
    <?php endif; ?>
</section>

</div>

<script>
if (typeof Chart === 'undefined') {
    showChartErrors(['dailyChartError', 'monthlyChartError', 'weeklyChartError', 'intradayChartError']);
}

const dailyLabels = <?= json_encode($daily_labels) ?>;
const dailyValues = <?= json_encode($daily_values) ?>;
const monthlyLabels = <?= json_encode($monthly_labels) ?>;
const monthlyValues = <?= json_encode($monthly_values) ?>;
const weeklyLabels = <?= json_encode($weekly_labels) ?>;
const weeklyValues = <?= json_encode($weekly_values) ?>;
const intradayLabels = <?= json_encode($intraday_labels) ?>;
const intradayValues = <?= json_encode($intraday_values) ?>;
const targetPrice = <?= $target_price !== null ? json_encode((float) $target_price) : 'null' ?>;
const invalidationPrice = <?= $invalidation_price !== null ? json_encode((float) $invalidation_price) : 'null' ?>;

// [FIX 24/09] Questo blocco duplicava per intero eurTick/sparseTicks/buildChart
// già estratte in assets/charts.js il 19/09 (commento del refactor diceva
// "riusate da grafico.php" ma la copia locale non era mai stata rimossa).
// La copia locale, a differenza di quella in charts.js, non aveva la guardia
// "typeof Chart !== 'undefined'" sulle righe Chart.defaults: se Chart.js non
// si carica, il guard sopra mostra correttamente l'avviso ma execution
// continua fino a queste righe, che avrebbero comunque fallito con un
// ReferenceError. Rimossa la copia: si usano solo le funzioni condivise
// (già caricate da assets/charts.js) per evitare che le due versioni
// divergano di nuovo in futuro.
buildChart('dailyChart', dailyLabels, dailyValues, '#4f46e5', 'rgba(79,70,229,0.08)', 'Prezzo close', targetPrice, invalidationPrice);
buildChart('monthlyChart', monthlyLabels, monthlyValues, '#0891b2', 'rgba(8,145,178,0.08)', 'Prezzo close', null, null);
buildChart('weeklyChart', weeklyLabels, weeklyValues, '#ea580c', 'rgba(234,88,12,0.08)', 'Prezzo close (15m)', null, null);
buildChart('intradayChart', intradayLabels, intradayValues, '#7c3aed', 'rgba(124,58,237,0.08)', 'Prezzo close (15m)', null, null);
</script>

<footer>SAPTA · <?= e($ticker) ?> · Pagina generata <?= date('d/m/Y H:i') ?></footer>
</body>
</html>
