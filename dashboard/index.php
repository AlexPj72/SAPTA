<?php
require_once 'config.php';

// Ultimi segnali filtrati (Modulo E)
$signals = supabase_query('signals_filtered', [
    'select' => '*',
    'order' => 'timestamp.desc',
    'limit' => 20
]);

// Candidati screening recenti (Modulo H v5.1.1 — sostituisce la vecchia tabella "anomalies")
$candidates = supabase_query('screening_candidates', [
    'select' => '*',
    'order' => 'timestamp.desc',
    'limit' => 15
]);

// Capitale corrente (tabella capital_state)
$capital_history = supabase_query('capital_state', [
    'select' => 'capital_eur,created_at',
    'order' => 'created_at.desc',
    'limit' => 1
]);
$current_capital = $capital_history[0]['capital_eur'] ?? null;
?>
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>SAPTA Dashboard</title>
    <link rel="stylesheet" href="assets/style.css">
</head>
<body>
    <header>
        <h1>SAPTA v5.1.1 — Dashboard</h1>
        <p>
            Capitale corrente:
            <strong><?= $current_capital !== null ? '€' . number_format($current_capital, 2) : 'Non impostato' ?></strong>
            — <a href="capital.php" style="color:#fff;">gestisci capitale</a>
            — <a href="decisions.php" style="color:#fff;">decisioni (paper trading)</a>
        </p>
        <p>Ultimo aggiornamento pagina: <?= date('d/m/Y H:i') ?></p>
    </header>

    <section>
        <h2>Segnali Filtrati (ultimi 20)</h2>
        <table>
            <thead>
                <tr>
                    <th>Timestamp</th>
                    <th>Ticker</th>
                    <th>Azione Originale</th>
                    <th>Azione Filtrata</th>
                    <th>Rendimento Netto Atteso</th>
                    <th>Target / Invalidation</th>
                    <th>Stato</th>
                </tr>
            </thead>
            <tbody>
                <?php if (empty($signals)): ?>
                <tr><td colspan="6">Nessun segnale disponibile.</td></tr>
                <?php endif; ?>
                <?php foreach ($signals as $s): ?>
                <tr>
                    <td><?= date('d/m H:i', strtotime($s['timestamp'])) ?></td>
                    <td><strong><a href="grafico.php?ticker=<?= urlencode($s['ticker']) ?>"><?= htmlspecialchars($s['ticker']) ?></a></strong></td>
                    <td><?= htmlspecialchars($s['original_action']) ?></td>
                    <td class="<?= $s['filtered_action'] === 'HOLD' ? 'declassato' : '' ?>">
                        <?= htmlspecialchars($s['filtered_action']) ?>
                    </td>
                    <td><?= number_format(($s['expected_net_return'] ?? 0) * 100, 2) ?>%</td>
                    <td>
                        <?= isset($s['target_price']) ? '🎯 €' . number_format($s['target_price'], 2) : '—' ?><br>
                        <?= isset($s['invalidation_price']) ? '🛑 €' . number_format($s['invalidation_price'], 2) : '—' ?>
                    </td>
                    <td>
                        <?php if ($s['filtered_action'] === 'HOLD' && $s['original_action'] === 'HOLD'): ?>
                            <span class="badge hold">— nessuna azione</span>
                        <?php elseif (!empty($s['filter_passed'])): ?>
                            <span class="badge approved">✅ APPROVATO</span>
                            <br><a href="decisions.php?ticker=<?= urlencode($s['ticker']) ?>&signal_id=<?= (int) $s['id'] ?>">registra decisione</a>
                        <?php else: ?>
                            <span class="badge rejected">❌ DECLASSATO</span>
                            <br><small><?= htmlspecialchars($s['filter_reason'] ?? '') ?></small>
                        <?php endif; ?>
                    </td>
                </tr>
                <?php endforeach; ?>
            </tbody>
        </table>
    </section>

    <section>
        <h2>Candidati Screening (Modulo H, ultimi 15)</h2>
        <table>
            <thead>
                <tr>
                    <th>Timestamp</th>
                    <th>Ticker</th>
                    <th>Status</th>
                    <th>Fascia Liquidità</th>
                    <th>News (livello 1)</th>
                    <th>Context Score</th>
                </tr>
            </thead>
            <tbody>
                <?php if (empty($candidates)): ?>
                <tr><td colspan="6">Nessun candidato disponibile (normale a mercato chiuso).</td></tr>
                <?php endif; ?>
                <?php foreach ($candidates as $c): ?>
                <tr>
                    <td><?= date('d/m H:i', strtotime($c['timestamp'])) ?></td>
                    <td><strong><?= htmlspecialchars($c['ticker']) ?></strong></td>
                    <td><?= htmlspecialchars($c['status'] ?? '') ?></td>
                    <td><?= htmlspecialchars($c['liquidity_bucket'] ?? '') ?></td>
                    <td><?= isset($c['news_light_count']) ? (int)$c['news_light_count'] : '—' ?></td>
                    <td><?= isset($c['context_score']) ? number_format($c['context_score'], 2) : '—' ?></td>
                </tr>
                <?php endforeach; ?>
            </tbody>
        </table>
    </section>
</body>
</html>
