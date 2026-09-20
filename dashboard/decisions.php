<?php
require_once 'config.php';
require_once 'helpers.php';

$message = '';
$message_error = false;

// --- Submit: nuova decisione (apertura) ---
if ($_SERVER['REQUEST_METHOD'] === 'POST' && ($_POST['action'] ?? '') === 'new_decision') {
    $ticker = trim($_POST['ticker'] ?? '');
    $decision = $_POST['decision'] ?? '';
    $reason = trim($_POST['reason'] ?? '');
    $execution_price = (float) str_replace(',', '.', $_POST['execution_price'] ?? '0');
    $signal_id = $_POST['signal_id'] !== '' ? (int) $_POST['signal_id'] : null;

    if ($ticker !== '' && in_array($decision, ['BUY', 'SELL'], true) && $execution_price > 0) {
        $code = supabase_write('human_decisions', [
            'signal_id' => $signal_id,
            'ticker' => $ticker,
            'timestamp_received' => date('c'),
            'timestamp_decision' => date('c'),
            'decision' => $decision,
            'reason' => $reason,
            'execution_price' => $execution_price,
            'execution_timestamp' => date('c'),
        ]);
        $message = $code === 201 ? "Decisione registrata: $decision $ticker a €$execution_price" : "Errore nella registrazione (HTTP $code)";
        $message_error = $code !== 201;
    } else {
        $message = "Compila ticker, decisione (BUY/SELL) e prezzo di esecuzione";
        $message_error = true;
    }
}

// --- Submit: chiusura posizione aperta ---
if ($_SERVER['REQUEST_METHOD'] === 'POST' && ($_POST['action'] ?? '') === 'close_decision') {
    $id = (int) ($_POST['id'] ?? 0);
    $close_price = (float) str_replace(',', '.', $_POST['close_price'] ?? '0');
    $close_reason = trim($_POST['close_reason'] ?? '');

    if ($id > 0 && $close_price > 0) {
        $existing = supabase_query('human_decisions', ['select' => 'execution_price,decision', 'id' => 'eq.' . $id]);
        $exec_price = $existing[0]['execution_price'] ?? null;
        $side = $existing[0]['decision'] ?? null;
        $pnl = null;
        if ($exec_price !== null && $side !== null) {
            $pnl = $side === 'BUY' ? ($close_price - $exec_price) : ($exec_price - $close_price);
        }
        $code = supabase_write('human_decisions', [
            'close_price' => $close_price,
            'close_timestamp' => date('c'),
            'close_reason' => $close_reason,
            'pnl_eur' => $pnl,
        ], 'PATCH', '?id=eq.' . $id);
        $message = in_array($code, [200, 204], true)
            ? "Posizione chiusa" . ($pnl !== null ? " (P&L: " . fmt_eur($pnl) . ")" : '')
            : "Errore nella chiusura (HTTP $code)";
        $message_error = !in_array($code, [200, 204], true);
    } else {
        $message = "Inserisci un prezzo di chiusura valido";
        $message_error = true;
    }
}

$prefill_ticker = $_GET['ticker'] ?? '';
$prefill_signal_id = $_GET['signal_id'] ?? '';

// Se si arriva da un segnale specifico, recupera la spiegazione per guidare la decisione
$origin_signal = null; $origin_candidate = null;
if ($prefill_signal_id !== '') {
    $rows = supabase_query('signals_filtered', ['select' => '*', 'id' => 'eq.' . (int) $prefill_signal_id, 'limit' => 1]);
    $origin_signal = $rows[0] ?? null;
    if ($origin_signal && !empty($origin_signal['screening_candidate_id'])) {
        $c = supabase_query('screening_candidates', ['select' => '*', 'id' => 'eq.' . $origin_signal['screening_candidate_id'], 'limit' => 1]);
        $origin_candidate = $c[0] ?? null;
    }
}

// [NUOVO 19/09] Storico completo delle chiuse, in ordine cronologico - serve
// sia per la curva P&L/win-rate nel tempo sia per calcolare i KPI su TUTTO
// lo storico invece che solo sulle ultime 15 (fix di un bug minore: prima
// pnl_totale/win_rate erano calcolati solo sulle ultime 15 chiuse, non sul
// vero totale).
$all_closed = supabase_query('human_decisions', ['select' => '*', 'close_price' => 'not.is.null', 'order' => 'close_timestamp.asc', 'limit' => 500]);
$closed_positions = array_reverse(array_slice($all_closed, -15)); // ultime 15, più recenti prima, per la tabella

$open_positions = supabase_query('human_decisions', ['select' => '*', 'close_price' => 'is.null', 'order' => 'timestamp_decision.desc']);

$n_open = count($open_positions);
$n_closed = count($all_closed);
$pnl_totale = array_sum(array_map(fn($p) => (float) ($p['pnl_eur'] ?? 0), $all_closed));
$win_count = count(array_filter($all_closed, fn($p) => ($p['pnl_eur'] ?? 0) > 0));

// Curva P&L cumulato + win rate cumulato, un punto per ogni posizione chiusa in ordine cronologico
$curve_labels = []; $pnl_curve = []; $winrate_curve = [];
$running_pnl = 0.0; $running_wins = 0;
foreach ($all_closed as $i => $p) {
    $running_pnl += (float) ($p['pnl_eur'] ?? 0);
    $running_wins += (($p['pnl_eur'] ?? 0) > 0) ? 1 : 0;
    $curve_labels[] = date('d/m', strtotime($p['close_timestamp']));
    $pnl_curve[] = round($running_pnl, 2);
    $winrate_curve[] = round($running_wins / ($i + 1) * 100, 1);
}
?>
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>SAPTA — Paper Trading</title>
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
            <h1>Paper trading guidato</h1>
            <p>Registra qui le tue decisioni "a soldi finti" — ti serve a validare il sistema prima di usare capitale vero.</p>
        </div>
        <a class="back-link" href="index.php">← Dashboard</a>
    </div>
</header>

<div class="stat-grid">
    <div class="stat-card">
        <div class="stat-label">Posizioni aperte</div>
        <div class="stat-value"><?= $n_open ?></div>
    </div>
    <div class="stat-card">
        <div class="stat-label">Posizioni chiuse</div>
        <div class="stat-value"><?= $n_closed ?></div>
    </div>
    <div class="stat-card <?= $pnl_totale >= 0 ? 'good' : 'bad' ?>">
        <div class="stat-label">P&amp;L totale (chiuse)</div>
        <div class="stat-value"><?= fmt_eur($pnl_totale) ?></div>
    </div>
    <div class="stat-card">
        <div class="stat-label">Win rate</div>
        <div class="stat-value"><?= $n_closed > 0 ? round($win_count / $n_closed * 100) . '%' : '—' ?></div>
        <div class="stat-sub"><?= $win_count ?>/<?= $n_closed ?> chiuse in guadagno</div>
    </div>
</div>

<?php render_nav('decisions.php'); ?>

<div class="wrap">

<?php if ($n_closed >= 2): ?>
<section class="chart-card">
    <div class="section-head">
        <div><h2>Andamento nel tempo</h2><p class="muted">Curva P&amp;L cumulato e win rate su tutte le <?= $n_closed ?> posizioni chiuse — non solo il totale attuale.</p></div>
    </div>
    <div class="chart-wrap" style="height:260px;"><canvas id="pnlCurveChart"></canvas></div>
    <div id="pnlCurveChartError" class="chart-error" style="display:none; margin-top:10px;">⚠️ Grafico non caricato.</div>
    <div class="chart-legend-row"><span><i style="background:#4f46e5"></i> P&amp;L cumulato (€)</span></div>

    <div class="chart-wrap" style="height:200px; margin-top:20px;"><canvas id="winrateCurveChart"></canvas></div>
    <div id="winrateCurveChartError" class="chart-error" style="display:none; margin-top:10px;">⚠️ Grafico non caricato.</div>
    <div class="chart-legend-row"><span><i style="background:#16a34a"></i> Win rate cumulato (%)</span></div>
</section>
<script>
if (typeof Chart === 'undefined') { showChartErrors(['pnlCurveChartError', 'winrateCurveChartError']); }
buildChart('pnlCurveChart', <?= json_encode($curve_labels) ?>, <?= json_encode($pnl_curve) ?>, '#4f46e5', 'rgba(79,70,229,0.08)', 'P&L cumulato', null, null);
buildChart('winrateCurveChart', <?= json_encode($curve_labels) ?>, <?= json_encode($winrate_curve) ?>, '#16a34a', 'rgba(22,163,74,0.08)', 'Win rate cumulato', null, null, 'pct');
</script>
<?php else: ?>
<section>
    <p class="muted">La curva P&amp;L nel tempo compare da almeno 2 posizioni chiuse — registrane qualcuna per iniziare a vederla.</p>
</section>
<?php endif; ?>

<section>
    <h2>Come funziona, passo dopo passo</h2>
    <p class="muted">Segui questi passaggi ogni volta che vuoi valutare un'opportunità.</p>
    <ul class="step-list">
        <li>
            <div class="step-num">1</div>
            <div class="step-body"><b>Guarda i segnali approvati</b><span>Dalla <a href="index.php">dashboard</a>, solo quelli con badge "✅ approvato" sono passati tutti i filtri di costo e rischio.</span></div>
        </li>
        <li>
            <div class="step-num">2</div>
            <div class="step-body"><b>Leggi il "perché"</b><span>Apri la spiegazione di ogni segnale: tipo di opportunità, confidenza, contesto macro/GDELT, notizie recenti, rischio di portafoglio.</span></div>
        </li>
        <li>
            <div class="step-num">3</div>
            <div class="step-body"><b>Se sei convinto, registra l'apertura qui sotto</b><span>Usa il prezzo reale che vedresti nel tuo broker in quel momento, non quello del segnale (può essere di qualche minuto fa).</span></div>
        </li>
        <li>
            <div class="step-num">4</div>
            <div class="step-body"><b>Monitora la posizione aperta</b><span>Controlla il grafico del titolo: se tocca il target (🎯) o l'invalidazione (🛑), è il momento di chiudere.</span></div>
        </li>
        <li>
            <div class="step-num">5</div>
            <div class="step-body"><b>Chiudi e registra il risultato</b><span>Il P&L si calcola da solo. Con abbastanza posizioni chiuse (Win rate qui sopra) potrai giudicare se il sistema è pronto per soldi veri.</span></div>
        </li>
    </ul>
</section>

<?php if ($message): ?>
<div class="flash"><div class="flash-msg<?= $message_error ? ' error' : '' ?>"><?= e($message) ?></div></div>
<?php endif; ?>

<?php if ($origin_signal): ?>
<section>
    <h2>Segnale selezionato: <?= e($origin_signal['ticker']) ?> <?= badge_azione($origin_signal['filtered_action'] ?? '') ?></h2>
    <div class="explain" style="max-width:none;"><?= spiega_segnale($origin_signal, $origin_candidate) ?></div>
</section>
<?php endif; ?>

<section>
    <h2>Registra nuova decisione</h2>
    <form method="POST" class="form-grid">
        <input type="hidden" name="action" value="new_decision">
        <div class="field"><label>Ticker</label><input type="text" name="ticker" value="<?= e($prefill_ticker) ?>" required></div>
        <div class="field"><label>Signal ID (opzionale)</label><input type="number" name="signal_id" value="<?= e($prefill_signal_id) ?>"></div>
        <div class="field"><label>Decisione</label>
            <select name="decision"><option value="BUY">BUY</option><option value="SELL">SELL</option></select>
        </div>
        <div class="field"><label>Prezzo di esecuzione (€)</label><input type="text" name="execution_price" required></div>
        <div class="field" style="grid-column: 1 / -1;"><label>Motivazione (opzionale)</label><input type="text" name="reason" placeholder="es. confermato anche dal contesto GDELT"></div>
        <div><button type="submit">Registra decisione</button></div>
    </form>
</section>

<section>
    <div class="section-head"><h2>Posizioni aperte</h2></div>
    <div class="table-wrap">
    <table>
        <thead><tr><th>Apertura</th><th>Ticker</th><th>Lato</th><th>Prezzo</th><th>Motivazione</th><th>Chiudi</th></tr></thead>
        <tbody>
        <?php if (empty($open_positions)): ?><tr><td colspan="6" class="empty-state">Nessuna posizione aperta.</td></tr><?php endif; ?>
        <?php foreach ($open_positions as $p): ?>
        <tr>
            <td><?= e(date('d/m/Y H:i', strtotime($p['timestamp_decision']))) ?></td>
            <td><a class="ticker-link" href="grafico.php?ticker=<?= urlencode($p['ticker']) ?>"><?= e($p['ticker']) ?></a></td>
            <td><?= badge_azione($p['decision']) ?></td>
            <td><?= fmt_eur($p['execution_price']) ?></td>
            <td class="muted"><?= e($p['reason'] ?? '') ?></td>
            <td>
                <form method="POST" style="display:flex; gap:6px;">
                    <input type="hidden" name="action" value="close_decision">
                    <input type="hidden" name="id" value="<?= (int) $p['id'] ?>">
                    <input type="text" name="close_price" placeholder="prezzo" style="width:90px;" required>
                    <button type="submit" class="btn-secondary">Chiudi</button>
                </form>
            </td>
        </tr>
        <?php endforeach; ?>
        </tbody>
    </table>
    </div>
</section>

<section>
    <div class="section-head"><h2>Storico chiuse (ultime 15)</h2></div>
    <div class="table-wrap">
    <table>
        <thead><tr><th>Chiusura</th><th>Ticker</th><th>Lato</th><th>Apertura</th><th>Chiusura</th><th>P&amp;L</th></tr></thead>
        <tbody>
        <?php if (empty($closed_positions)): ?><tr><td colspan="6" class="empty-state">Nessuna posizione chiusa.</td></tr><?php endif; ?>
        <?php foreach ($closed_positions as $p): ?>
        <tr>
            <td><?= e(date('d/m/Y H:i', strtotime($p['close_timestamp']))) ?></td>
            <td><a class="ticker-link" href="grafico.php?ticker=<?= urlencode($p['ticker']) ?>"><?= e($p['ticker']) ?></a></td>
            <td><?= badge_azione($p['decision']) ?></td>
            <td><?= fmt_eur($p['execution_price']) ?></td>
            <td><?= fmt_eur($p['close_price']) ?></td>
            <td class="<?= ($p['pnl_eur'] ?? 0) >= 0 ? 'positive' : 'negative' ?>"><?= fmt_eur($p['pnl_eur'] ?? 0) ?></td>
        </tr>
        <?php endforeach; ?>
        </tbody>
    </table>
    </div>
</section>

</div>

<footer>SAPTA · Paper trading · Pagina generata <?= date('d/m/Y H:i') ?></footer>
</body>
</html>
