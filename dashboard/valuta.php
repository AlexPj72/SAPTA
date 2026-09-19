<?php
require_once 'config.php';
require_once 'helpers.php';

$ticker = $_GET['ticker'] ?? '';
$kind = $_GET['kind'] ?? '';
$id = isset($_GET['id']) ? (int) $_GET['id'] : 0;
if ($ticker === '') { die('Ticker mancante. <a href="today.php">Torna a "Da valutare oggi"</a>'); }

// Segnale operativo: quello specifico se arrivo da un link con id, altrimenti l'ultimo attivo per il ticker
$signal = null;
if ($kind === 'segnale' && $id) {
    $rows = supabase_query('signals_filtered', ['select' => '*', 'id' => 'eq.' . $id, 'limit' => 1]);
    $signal = $rows[0] ?? null;
}
if (!$signal) {
    $rows = supabase_query('signals_filtered', [
        'select' => '*', 'ticker' => 'eq.' . $ticker, 'filtered_action' => 'neq.HOLD',
        'filter_passed' => 'eq.true', 'order' => 'timestamp.desc', 'limit' => 1,
    ]);
    $signal = $rows[0] ?? null;
}
$candidate = null;
if ($signal && !empty($signal['screening_candidate_id'])) {
    $rows = supabase_query('screening_candidates', ['select' => '*', 'id' => 'eq.' . $signal['screening_candidate_id'], 'limit' => 1]);
    $candidate = $rows[0] ?? null;
}

// Ipotesi AI Watch: quella specifica se arrivo da un link con id, altrimenti l'ultima di oggi per il ticker
$hypothesis = null;
if ($kind === 'ipotesi' && $id) {
    $rows = supabase_query('ai_hypotheses', ['select' => '*', 'id' => 'eq.' . $id, 'limit' => 1]);
    $hypothesis = $rows[0] ?? null;
}
if (!$hypothesis) {
    $rows = supabase_query('ai_hypotheses', [
        'select' => '*', 'ticker' => 'eq.' . $ticker, 'hypothesis_date' => 'eq.' . date('Y-m-d'),
        'order' => 'created_at.desc', 'limit' => 1,
    ]);
    $hypothesis = $rows[0] ?? null;
}

// Grafico: storico 60gg + sessione intraday corrente (versione ridotta di grafico.php,
// per una pagina guidata più leggera - il link "grafico completo" porta a tutto il resto)
$daily = supabase_query('prezzi', ['select' => 'timestamp,close', 'ticker' => 'eq.' . $ticker, 'interval' => 'eq.1d', 'order' => 'timestamp.desc', 'limit' => 60]);
$daily = array_reverse($daily);
$intraday_raw = supabase_query('prezzi', ['select' => 'timestamp,close', 'ticker' => 'eq.' . $ticker, 'interval' => 'eq.15m', 'order' => 'timestamp.desc', 'limit' => 60]);
$last_session_date = !empty($intraday_raw) ? substr($intraday_raw[0]['timestamp'], 0, 10) : null;
$intraday = array_values(array_filter($intraday_raw, fn($r) => substr($r['timestamp'], 0, 10) === $last_session_date));
$intraday = array_reverse($intraday);

$daily_labels = array_map(fn($d) => date('d/m', strtotime($d['timestamp'])), $daily);
$daily_values = array_map(fn($d) => (float) $d['close'], $daily);
$intraday_labels = array_map(fn($d) => date('H:i', strtotime($d['timestamp'])), $intraday);
$intraday_values = array_map(fn($d) => (float) $d['close'], $intraday);
$target_price = $signal['target_price'] ?? null;
$invalidation_price = $signal['invalidation_price'] ?? null;
$market = market_status($ticker);
?>
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>SAPTA — Valuta <?= e($ticker) ?></title>
    <link rel="stylesheet" href="assets/style.css">
    <script src="assets/chart.umd.min.js"></script>
    <script src="assets/charts.js"></script>
</head>
<body>

<header class="hero compact">
    <div class="hero-top">
        <div>
            <div class="eyebrow">Decisione guidata</div>
            <h1><?= market_flag($ticker) ?> <?= e($ticker) ?></h1>
            <p><span class="badge <?= $market['aperto'] ? 'approved' : 'hold' ?>"><?= $market['aperto'] ? '🟢' : '⚪' ?> <?= e($market['label']) ?></span></p>
        </div>
        <a class="back-link" href="today.php">← Da valutare oggi</a>
    </div>
</header>

<div class="wrap">

<section>
    <ul class="step-list">
        <li class="done"><div class="step-num">1</div><div class="step-body"><b>Guarda il grafico</b><span>Storico e sessione di oggi, qui sotto.</span></div></li>
        <li class="done"><div class="step-num">2</div><div class="step-body"><b>Leggi perché è stato segnalato</b><span>Sezione "Perché" più sotto.</span></div></li>
        <li class="done"><div class="step-num">3</div><div class="step-body"><b>Controlla il rischio</b><span>Esposizione e concentrazione, se già calcolati.</span></div></li>
        <li><div class="step-num">4</div><div class="step-body"><b>Decidi e registra</b><span>Form in fondo alla pagina.</span></div></li>
    </ul>
</section>

<section class="chart-card">
    <div class="section-head">
        <div><h2>Grafico</h2><p class="muted">Storico 60gg + sessione di oggi · <a href="grafico.php?ticker=<?= urlencode($ticker) ?>">grafico completo con trend settimanale/mensile →</a></p></div>
    </div>
    <?php if (empty($daily)): ?>
        <p class="muted">Nessuno storico disponibile.</p>
    <?php else: ?>
        <div class="chart-wrap" style="height:260px;"><canvas id="dailyChart"></canvas></div>
        <div id="dailyChartError" class="chart-error" style="display:none; margin-top:10px;">⚠️ Grafico non caricato (Chart.js non disponibile).</div>
    <?php endif; ?>
    <?php if (!empty($intraday)): ?>
        <div class="chart-wrap" style="height:200px; margin-top:16px;"><canvas id="intradayChart"></canvas></div>
        <div id="intradayChartError" class="chart-error" style="display:none; margin-top:10px;">⚠️ Grafico non caricato.</div>
    <?php endif; ?>
</section>

<section>
    <h2>Perché è stato segnalato</h2>
    <?php if ($signal): ?>
        <div class="explain" style="max-width:none;"><?= spiega_segnale($signal, $candidate) ?></div>
    <?php elseif ($hypothesis): ?>
        <div class="explain" style="max-width:none;">
            <b><?= $hypothesis['status'] === 'confermato' ? '✅ Ipotesi confermata' : '👀 Ipotesi in osservazione' ?>.</b>
            <?= e($hypothesis['motivazione']) ?>
            <?php if (($hypothesis['status'] ?? '') === 'confermato'): ?>
                Direzione mantenuta dopo <?= (int) $hypothesis['checked_count'] ?> ricontrolli
                (variazione attuale <?= number_format($hypothesis['price_change_pct_latest'] ?? 0, 2) ?>%,
                era <?= number_format($hypothesis['price_change_pct'], 2) ?>% all'alert iniziale).
            <?php endif; ?>
            Resta un'osservazione qualitativa, <b>non un segnale operativo</b> — nessun target/stop calcolato da SAPTA per questa ipotesi.
        </div>
    <?php else: ?>
        <p class="muted">Nessun segnale o ipotesi trovati per questo ticker in questo momento.</p>
    <?php endif; ?>
</section>

<section>
    <h2>Rischio</h2>
    <?php if ($signal && (isset($signal['sector_concentration_count']) || isset($signal['portfolio_exposure_pct']))): ?>
        <div class="stat-grid" style="margin:0; padding:0; position:static;">
            <div class="stat-card">
                <div class="stat-label">Concentrazione settoriale</div>
                <div class="stat-value"><?= (int) ($signal['sector_concentration_count'] ?? 0) ?></div>
                <div class="stat-sub">posizioni già aperte nello stesso settore</div>
            </div>
            <div class="stat-card <?= ($signal['portfolio_exposure_pct'] ?? 0) > 0.5 ? 'warn' : '' ?>">
                <div class="stat-label">Esposizione stimata</div>
                <div class="stat-value"><?= number_format(($signal['portfolio_exposure_pct'] ?? 0) * 100, 0) ?>%</div>
                <div class="stat-sub">del capitale, se eseguita insieme alle altre aperte</div>
            </div>
        </div>
    <?php else: ?>
        <p class="muted">Nessun controllo di rischio di portafoglio calcolato per questo elemento (i controlli di Sezione 15 si applicano solo ai segnali operativi reali, non alle ipotesi qualitative).</p>
    <?php endif; ?>
</section>

<section>
    <h2>Registra la tua decisione</h2>
    <p class="muted">Il modulo va alla pagina di paper trading — usa il prezzo reale che vedi ora, non quello dell'alert.</p>
    <form method="POST" action="decisions.php" class="form-grid">
        <input type="hidden" name="action" value="new_decision">
        <input type="hidden" name="ticker" value="<?= e($ticker) ?>">
        <input type="hidden" name="signal_id" value="<?= $signal ? (int) $signal['id'] : '' ?>">
        <div class="field"><label>Decisione</label>
            <select name="decision">
                <option value="BUY" <?= ($signal['filtered_action'] ?? '') === 'BUY' ? 'selected' : '' ?>>BUY</option>
                <option value="SELL" <?= ($signal['filtered_action'] ?? '') === 'SELL' ? 'selected' : '' ?>>SELL</option>
            </select>
        </div>
        <div class="field"><label>Prezzo di esecuzione (€)</label><input type="text" name="execution_price" required></div>
        <div class="field" style="grid-column: 1 / -1;"><label>Motivazione (opzionale)</label><input type="text" name="reason" placeholder="es. confermato dal grafico, entro"></div>
        <div><button type="submit">Registra decisione</button></div>
    </form>
    <p class="muted" style="margin-top:14px;">Oppure, se dopo aver valutato preferisci non fare nulla, va benissimo — torna semplicemente a <a href="today.php">"Da valutare oggi"</a>.</p>
</section>

</div>

<script>
if (typeof Chart === 'undefined') { showChartErrors(['dailyChartError', 'intradayChartError']); }
buildChart('dailyChart', <?= json_encode($daily_labels) ?>, <?= json_encode($daily_values) ?>, '#4f46e5', 'rgba(79,70,229,0.08)', 'Prezzo close',
    <?= $target_price !== null ? json_encode((float) $target_price) : 'null' ?>,
    <?= $invalidation_price !== null ? json_encode((float) $invalidation_price) : 'null' ?>);
buildChart('intradayChart', <?= json_encode($intraday_labels) ?>, <?= json_encode($intraday_values) ?>, '#7c3aed', 'rgba(124,58,237,0.08)', 'Prezzo close (15m)', null, null);
</script>

<footer>SAPTA · Decisione guidata · <?= e($ticker) ?></footer>
</body>
</html>
