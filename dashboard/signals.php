<?php
require_once 'config.php';

$raw_signals = supabase_query('signals_raw', [
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
    <title>SAPTA — Segnali Dettagliati</title>
    <link rel="stylesheet" href="assets/style.css">
</head>
<body>
    <header>
        <h1>SAPTA — Segnali Dettagliati (Modulo B)</h1>
        <p><a href="index.php" style="color:#fff;">&larr; torna alla dashboard</a></p>
    </header>

    <section>
        <h2>Ultimi 30 segnali grezzi</h2>
        <table>
            <thead>
                <tr>
                    <th>Timestamp</th>
                    <th>Ticker</th>
                    <th>Azione</th>
                    <th>Tipologia</th>
                    <th>Confidenza</th>
                    <th>Prezzo</th>
                    <th>Invalidazione</th>
                    <th>Earnings imminenti</th>
                    <th>Barra provv.</th>
                </tr>
            </thead>
            <tbody>
                <?php if (empty($raw_signals)): ?>
                <tr><td colspan="9">Nessun segnale disponibile.</td></tr>
                <?php endif; ?>
                <?php foreach ($raw_signals as $s): ?>
                <tr>
                    <td><?= date('d/m H:i', strtotime($s['timestamp'])) ?></td>
                    <td><strong><?= htmlspecialchars($s['ticker']) ?></strong></td>
                    <td><?= htmlspecialchars($s['action']) ?></td>
                    <td><?= htmlspecialchars($s['opportunity_type'] ?? '—') ?></td>
                    <td>
                        <?= htmlspecialchars($s['confidence_level'] ?? '—') ?>
                        <?php if (isset($s['confidence_multiplier'])): ?>
                            (x<?= number_format($s['confidence_multiplier'], 1) ?>)
                        <?php endif; ?>
                    </td>
                    <td><?= isset($s['close_price']) ? number_format($s['close_price'], 2) : '—' ?></td>
                    <td>
                        <?php if (isset($s['invalidation_price'])): ?>
                            <?= number_format($s['invalidation_price'], 2) ?>
                            <br><small><?= htmlspecialchars($s['invalidation_reason'] ?? '') ?></small>
                        <?php else: ?>
                            —
                        <?php endif; ?>
                    </td>
                    <td><?= !empty($s['has_upcoming_earnings']) ? '⚠️ Sì' : 'No' ?></td>
                    <td><?= !empty($s['is_provisional_bar']) ? '🟡 Provvisoria' : '✅ Definitiva' ?></td>
                </tr>
                <?php endforeach; ?>
            </tbody>
        </table>
    </section>
</body>
</html>
