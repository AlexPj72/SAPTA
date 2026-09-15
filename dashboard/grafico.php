<?php
require_once 'config.php';

$ticker = $_GET['ticker'] ?? '';
if ($ticker === '') {
    die('Ticker mancante. <a href="index.php">Torna alla dashboard</a>');
}

// Storico giornaliero (ultimi 90gg) - Modulo A
$daily = supabase_query('prezzi', [
    'select' => 'timestamp,close',
    'ticker' => 'eq.' . $ticker,
    'interval' => 'eq.1d',
    'order' => 'timestamp.desc',
    'limit' => 90
]);
$daily = array_reverse($daily); // ordine cronologico per il grafico

// Intraday 15m (ultime 100 barre)
$intraday = supabase_query('prezzi', [
    'select' => 'timestamp,close',
    'ticker' => 'eq.' . $ticker,
    'interval' => 'eq.15m',
    'order' => 'timestamp.desc',
    'limit' => 100
]);
$intraday = array_reverse($intraday);

// Ultimo segnale filtrato per questo ticker, per le linee target/invalidation
$last_signal = supabase_query('signals_filtered', [
    'select' => 'target_price,invalidation_price,filtered_action,timestamp',
    'ticker' => 'eq.' . $ticker,
    'order' => 'timestamp.desc',
    'limit' => 1
]);
$target_price = $last_signal[0]['target_price'] ?? null;
$invalidation_price = $last_signal[0]['invalidation_price'] ?? null;

$daily_labels = array_map(fn($d) => date('d/m', strtotime($d['timestamp'])), $daily);
$daily_values = array_map(fn($d) => (float) $d['close'], $daily);
$intraday_labels = array_map(fn($d) => date('d/m H:i', strtotime($d['timestamp'])), $intraday);
$intraday_values = array_map(fn($d) => (float) $d['close'], $intraday);
?>
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>SAPTA — Grafico <?= htmlspecialchars($ticker) ?></title>
    <link rel="stylesheet" href="assets/style.css">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.4/chart.umd.min.js"></script>
</head>
<body>
    <header>
        <h1>SAPTA — <?= htmlspecialchars($ticker) ?></h1>
        <p><a href="index.php" style="color:#fff;">&larr; torna alla dashboard</a></p>
        <?php if ($target_price || $invalidation_price): ?>
        <p>
            <?php if ($target_price): ?>🎯 Target: €<?= number_format($target_price, 2) ?> &nbsp; <?php endif; ?>
            <?php if ($invalidation_price): ?>🛑 Invalidation: €<?= number_format($invalidation_price, 2) ?><?php endif; ?>
        </p>
        <?php endif; ?>
    </header>

    <section>
        <h2>Storico giornaliero (ultimi 90gg)</h2>
        <?php if (empty($daily)): ?>
            <p>Nessuno storico giornaliero disponibile per questo ticker.</p>
        <?php else: ?>
            <canvas id="dailyChart" height="90"></canvas>
        <?php endif; ?>
    </section>

    <section>
        <h2>Intraday 15 minuti (ultime 100 barre)</h2>
        <?php if (empty($intraday)): ?>
            <p>Nessun dato intraday disponibile per questo ticker.</p>
        <?php else: ?>
            <canvas id="intradayChart" height="90"></canvas>
        <?php endif; ?>
    </section>

    <script>
        const dailyLabels = <?= json_encode($daily_labels) ?>;
        const dailyValues = <?= json_encode($daily_values) ?>;
        const intradayLabels = <?= json_encode($intraday_labels) ?>;
        const intradayValues = <?= json_encode($intraday_values) ?>;
        const targetPrice = <?= $target_price !== null ? json_encode((float) $target_price) : 'null' ?>;
        const invalidationPrice = <?= $invalidation_price !== null ? json_encode((float) $invalidation_price) : 'null' ?>;

        function buildLineDataset(label, values, color) {
            return { label, data: values, borderColor: color, tension: 0.1, pointRadius: 0 };
        }

        function addHorizontalLine(labels, value, label, color) {
            return { label, data: labels.map(() => value), borderColor: color, borderDash: [6, 4], pointRadius: 0 };
        }

        if (dailyValues.length) {
            const datasets = [buildLineDataset('Prezzo close', dailyValues, '#2563eb')];
            if (targetPrice !== null) datasets.push(addHorizontalLine(dailyLabels, targetPrice, 'Target', '#16a34a'));
            if (invalidationPrice !== null) datasets.push(addHorizontalLine(dailyLabels, invalidationPrice, 'Invalidation', '#dc2626'));
            new Chart(document.getElementById('dailyChart'), {
                type: 'line',
                data: { labels: dailyLabels, datasets },
            });
        }

        if (intradayValues.length) {
            const datasets = [buildLineDataset('Prezzo close (15m)', intradayValues, '#7c3aed')];
            if (targetPrice !== null) datasets.push(addHorizontalLine(intradayLabels, targetPrice, 'Target', '#16a34a'));
            if (invalidationPrice !== null) datasets.push(addHorizontalLine(intradayLabels, invalidationPrice, 'Invalidation', '#dc2626'));
            new Chart(document.getElementById('intradayChart'), {
                type: 'line',
                data: { labels: intradayLabels, datasets },
            });
        }
    </script>
</body>
</html>
