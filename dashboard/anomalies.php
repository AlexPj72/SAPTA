<?php
require_once 'config.php';

// NOTA: dal v5.1.1 la vecchia tabella "anomalies" non riceve più scritture
// (Modulo H è stato sostituito da H1/H2 che scrivono su screening_candidates).
// Questa pagina è stata aggiornata di conseguenza.
$candidates = supabase_query('screening_candidates', [
    'select' => '*',
    'order' => 'timestamp.desc',
    'limit' => 30
]);
?>
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>SAPTA — Radar Anomalie (H1/H2)</title>
    <link rel="stylesheet" href="assets/style.css">
</head>
<body>
    <header>
        <h1>SAPTA — Radar Anomalie (Modulo H, v5.1.1)</h1>
        <p><a href="index.php" style="color:#fff;">&larr; torna alla dashboard</a></p>
    </header>

    <section>
        <h2>Candidati screening (ultimi 30)</h2>
        <table>
            <thead>
                <tr>
                    <th>Timestamp</th>
                    <th>Ticker</th>
                    <th>Status</th>
                    <th>H1 Score</th>
                    <th>Anomaly Score</th>
                    <th>Context Score</th>
                    <th>Fascia Liquidità</th>
                    <th>Qualità Dato</th>
                    <th>News (livello 1)</th>
                </tr>
            </thead>
            <tbody>
                <?php if (empty($candidates)): ?>
                <tr><td colspan="9">Nessun candidato disponibile — normale a mercato chiuso o appena aperto (serve storico intraday minimo).</td></tr>
                <?php endif; ?>
                <?php foreach ($candidates as $c): ?>
                <tr>
                    <td><?= date('d/m H:i', strtotime($c['timestamp'])) ?></td>
                    <td><strong><?= htmlspecialchars($c['ticker']) ?></strong></td>
                    <td><?= htmlspecialchars($c['status'] ?? '') ?></td>
                    <td><?= isset($c['h1_score']) ? number_format($c['h1_score'], 2) : '—' ?></td>
                    <td><?= isset($c['anomaly_score']) ? number_format($c['anomaly_score'], 2) : '—' ?></td>
                    <td><?= isset($c['context_score']) ? number_format($c['context_score'], 2) : '—' ?></td>
                    <td><?= htmlspecialchars($c['liquidity_bucket'] ?? '—') ?></td>
                    <td><?= htmlspecialchars($c['data_quality_flag'] ?? '—') ?></td>
                    <td><?= isset($c['news_light_count']) ? (int)$c['news_light_count'] : '—' ?></td>
                </tr>
                <?php endforeach; ?>
            </tbody>
        </table>
    </section>
</body>
</html>
