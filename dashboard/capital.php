<?php
require_once 'config.php';

// Gestione submit form (impostazione nuovo capitale)
$message = '';
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['capital_eur'])) {
    $new_capital = (float) str_replace(',', '.', $_POST['capital_eur']);
    $change_type = $_POST['change_type'] ?? 'manual_set';
    $note = trim($_POST['note'] ?? '');

    if ($new_capital > 0) {
        $ch = curl_init(SUPABASE_URL . '/rest/v1/capital_state');
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_POST, true);
        curl_setopt($ch, CURLOPT_HTTPHEADER, [
            'apikey: ' . SUPABASE_ANON_KEY,
            'Authorization: Bearer ' . SUPABASE_ANON_KEY,
            'Content-Type: application/json',
            'Prefer: return=minimal'
        ]);
        curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode([
            'capital_eur' => $new_capital,
            'change_type' => $change_type,
            'note' => $note,
            'set_by' => 'dashboard'
        ]));
        curl_exec($ch);
        $http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);
        $message = $http_code === 201
            ? "✅ Capitale aggiornato a €" . number_format($new_capital, 2)
            : "❌ Errore nell'aggiornamento (HTTP $http_code)";
    } else {
        $message = "❌ Inserisci un valore maggiore di zero";
    }
}

// Capitale corrente e storico
$history = supabase_query('capital_state', [
    'select' => '*',
    'order' => 'created_at.desc',
    'limit' => 15
]);
$current = $history[0]['capital_eur'] ?? null;
?>
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>SAPTA — Gestione Capitale</title>
    <link rel="stylesheet" href="assets/style.css">
</head>
<body>
    <header>
        <h1>SAPTA — Capitale Operativo</h1>
        <p><a href="index.php" style="color:#fff;">&larr; torna alla dashboard</a></p>
    </header>

    <section>
        <h2>Capitale corrente</h2>
        <p style="font-size: 2em; font-weight: bold;">
            <?= $current !== null ? '€' . number_format($current, 2) : 'Non impostato' ?>
        </p>

        <?php if ($message): ?>
            <p><strong><?= htmlspecialchars($message) ?></strong></p>
        <?php endif; ?>

        <form method="POST">
            <label>Nuovo capitale (€): <input type="text" name="capital_eur" required></label><br><br>
            <label>Tipo:
                <select name="change_type">
                    <option value="manual_set">Impostazione manuale (es. inizio nuovo test)</option>
                    <option value="deposit">Deposito</option>
                    <option value="withdrawal">Prelievo</option>
                </select>
            </label><br><br>
            <label>Nota (opzionale): <input type="text" name="note" placeholder="es. test capitale ridotto"></label><br><br>
            <button type="submit">Aggiorna capitale</button>
        </form>
    </section>

    <section>
        <h2>Storico modifiche</h2>
        <table>
            <thead>
                <tr><th>Data</th><th>Capitale</th><th>Tipo</th><th>Nota</th></tr>
            </thead>
            <tbody>
                <?php if (empty($history)): ?>
                <tr><td colspan="4">Nessuno storico disponibile.</td></tr>
                <?php endif; ?>
                <?php foreach ($history as $h): ?>
                <tr>
                    <td><?= date('d/m/Y H:i', strtotime($h['created_at'])) ?></td>
                    <td>€<?= number_format($h['capital_eur'], 2) ?></td>
                    <td><?= htmlspecialchars($h['change_type']) ?></td>
                    <td><?= htmlspecialchars($h['note'] ?? '') ?></td>
                </tr>
                <?php endforeach; ?>
            </tbody>
        </table>
    </section>
</body>
</html>
