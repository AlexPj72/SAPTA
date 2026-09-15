<?php
require_once 'config.php';

$message = '';

// --- Submit: nuova decisione (apertura) ---
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['action']) && $_POST['action'] === 'new_decision') {
    $ticker = trim($_POST['ticker'] ?? '');
    $decision = $_POST['decision'] ?? '';
    $reason = trim($_POST['reason'] ?? '');
    $execution_price = (float) str_replace(',', '.', $_POST['execution_price'] ?? '0');
    $signal_id = $_POST['signal_id'] !== '' ? (int) $_POST['signal_id'] : null;

    if ($ticker !== '' && in_array($decision, ['BUY', 'SELL'], true) && $execution_price > 0) {
        $ch = curl_init(SUPABASE_URL . '/rest/v1/human_decisions');
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_POST, true);
        curl_setopt($ch, CURLOPT_HTTPHEADER, [
            'apikey: ' . SUPABASE_ANON_KEY,
            'Authorization: Bearer ' . SUPABASE_ANON_KEY,
            'Content-Type: application/json',
            'Prefer: return=minimal'
        ]);
        curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode([
            'signal_id' => $signal_id,
            'ticker' => $ticker,
            'timestamp_received' => date('c'),
            'timestamp_decision' => date('c'),
            'decision' => $decision,
            'reason' => $reason,
            'execution_price' => $execution_price,
            'execution_timestamp' => date('c'),
        ]));
        curl_exec($ch);
        $http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);
        $message = $http_code === 201
            ? "✅ Decisione registrata: $decision $ticker a €$execution_price"
            : "❌ Errore nella registrazione (HTTP $http_code)";
    } else {
        $message = "❌ Compila ticker, decisione (BUY/SELL) e prezzo di esecuzione";
    }
}

// --- Submit: chiusura posizione aperta ---
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['action']) && $_POST['action'] === 'close_decision') {
    $id = (int) ($_POST['id'] ?? 0);
    $close_price = (float) str_replace(',', '.', $_POST['close_price'] ?? '0');
    $close_reason = trim($_POST['close_reason'] ?? '');

    if ($id > 0 && $close_price > 0) {
        // Serve execution_price ed execution_side per calcolare il pnl: li leggiamo prima
        $existing = supabase_query('human_decisions', [
            'select' => 'execution_price,decision',
            'id' => 'eq.' . $id
        ]);
        $exec_price = $existing[0]['execution_price'] ?? null;
        $side = $existing[0]['decision'] ?? null;

        $pnl = null;
        if ($exec_price !== null && $side !== null) {
            $pnl = $side === 'BUY' ? ($close_price - $exec_price) : ($exec_price - $close_price);
        }

        $ch = curl_init(SUPABASE_URL . '/rest/v1/human_decisions?id=eq.' . $id);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_CUSTOMREQUEST, 'PATCH');
        curl_setopt($ch, CURLOPT_HTTPHEADER, [
            'apikey: ' . SUPABASE_ANON_KEY,
            'Authorization: Bearer ' . SUPABASE_ANON_KEY,
            'Content-Type: application/json',
            'Prefer: return=minimal'
        ]);
        curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode([
            'close_price' => $close_price,
            'close_timestamp' => date('c'),
            'close_reason' => $close_reason,
            'pnl_eur' => $pnl,
        ]));
        curl_exec($ch);
        $http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);
        $message = in_array($http_code, [200, 204], true)
            ? "✅ Posizione chiusa" . ($pnl !== null ? " (P&L: €" . number_format($pnl, 2) . ")" : '')
            : "❌ Errore nella chiusura (HTTP $http_code)";
    } else {
        $message = "❌ Inserisci un prezzo di chiusura valido";
    }
}

// Precompila ticker/signal_id se si arriva da un link della dashboard
$prefill_ticker = htmlspecialchars($_GET['ticker'] ?? '');
$prefill_signal_id = htmlspecialchars($_GET['signal_id'] ?? '');

// Posizioni aperte (close_price ancora nullo) e storico chiuse
$open_positions = supabase_query('human_decisions', [
    'select' => '*',
    'close_price' => 'is.null',
    'order' => 'timestamp_decision.desc'
]);
$closed_positions = supabase_query('human_decisions', [
    'select' => '*',
    'close_price' => 'not.is.null',
    'order' => 'close_timestamp.desc',
    'limit' => 15
]);
?>
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>SAPTA — Decisioni (Paper Trading)</title>
    <link rel="stylesheet" href="assets/style.css">
</head>
<body>
    <header>
        <h1>SAPTA — Decisioni (Paper Trading)</h1>
        <p><a href="index.php" style="color:#fff;">&larr; torna alla dashboard</a></p>
    </header>

    <?php if ($message): ?>
        <p><strong><?= htmlspecialchars($message) ?></strong></p>
    <?php endif; ?>

    <section>
        <h2>Registra nuova decisione</h2>
        <form method="POST">
            <input type="hidden" name="action" value="new_decision">
            <label>Ticker: <input type="text" name="ticker" value="<?= $prefill_ticker ?>" required></label><br><br>
            <label>Signal ID (opzionale, se apri da un segnale specifico):
                <input type="number" name="signal_id" value="<?= $prefill_signal_id ?>"></label><br><br>
            <label>Decisione:
                <select name="decision">
                    <option value="BUY">BUY</option>
                    <option value="SELL">SELL</option>
                </select>
            </label><br><br>
            <label>Prezzo di esecuzione (€): <input type="text" name="execution_price" required></label><br><br>
            <label>Motivazione (opzionale): <input type="text" name="reason" placeholder="es. conferma dal canale IA"></label><br><br>
            <button type="submit">Registra decisione</button>
        </form>
    </section>

    <section>
        <h2>Posizioni aperte</h2>
        <table>
            <thead>
                <tr>
                    <th>Data apertura</th><th>Ticker</th><th>Lato</th>
                    <th>Prezzo apertura</th><th>Motivazione</th><th>Chiudi</th>
                </tr>
            </thead>
            <tbody>
                <?php if (empty($open_positions)): ?>
                <tr><td colspan="6">Nessuna posizione aperta.</td></tr>
                <?php endif; ?>
                <?php foreach ($open_positions as $p): ?>
                <tr>
                    <td><?= date('d/m/Y H:i', strtotime($p['timestamp_decision'])) ?></td>
                    <td><strong><?= htmlspecialchars($p['ticker']) ?></strong></td>
                    <td><?= htmlspecialchars($p['decision']) ?></td>
                    <td>€<?= number_format($p['execution_price'], 2) ?></td>
                    <td><?= htmlspecialchars($p['reason'] ?? '') ?></td>
                    <td>
                        <form method="POST" style="display:flex; gap:4px;">
                            <input type="hidden" name="action" value="close_decision">
                            <input type="hidden" name="id" value="<?= (int) $p['id'] ?>">
                            <input type="text" name="close_price" placeholder="prezzo" style="width:80px;" required>
                            <button type="submit">Chiudi</button>
                        </form>
                    </td>
                </tr>
                <?php endforeach; ?>
            </tbody>
        </table>
    </section>

    <section>
        <h2>Storico chiuse (ultime 15)</h2>
        <table>
            <thead>
                <tr><th>Data chiusura</th><th>Ticker</th><th>Lato</th><th>Apertura</th><th>Chiusura</th><th>P&L</th></tr>
            </thead>
            <tbody>
                <?php if (empty($closed_positions)): ?>
                <tr><td colspan="6">Nessuna posizione chiusa.</td></tr>
                <?php endif; ?>
                <?php foreach ($closed_positions as $p): ?>
                <tr>
                    <td><?= date('d/m/Y H:i', strtotime($p['close_timestamp'])) ?></td>
                    <td><strong><?= htmlspecialchars($p['ticker']) ?></strong></td>
                    <td><?= htmlspecialchars($p['decision']) ?></td>
                    <td>€<?= number_format($p['execution_price'], 2) ?></td>
                    <td>€<?= number_format($p['close_price'], 2) ?></td>
                    <td class="<?= ($p['pnl_eur'] ?? 0) >= 0 ? 'approved' : 'rejected' ?>">
                        €<?= number_format($p['pnl_eur'] ?? 0, 2) ?>
                    </td>
                </tr>
                <?php endforeach; ?>
            </tbody>
        </table>
    </section>
</body>
</html>
