<?php
require_once 'config.php';
require_once 'helpers.php';

$message = ''; $message_error = false;
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['capital_eur'])) {
    $new_capital = (float) str_replace(',', '.', $_POST['capital_eur']);
    $change_type = $_POST['change_type'] ?? 'manual_set';
    $note = trim($_POST['note'] ?? '');

    if ($new_capital > 0) {
        $code = supabase_write('capital_state', [
            'capital_eur' => $new_capital,
            'change_type' => $change_type,
            'note' => $note,
            'set_by' => 'dashboard',
        ]);
        $message = $code === 201 ? "Capitale aggiornato a " . fmt_eur($new_capital) : "Errore nell'aggiornamento (HTTP $code)";
        $message_error = $code !== 201;
    } else {
        $message = "Inserisci un valore maggiore di zero";
        $message_error = true;
    }
}

$history = supabase_query('capital_state', ['select' => '*', 'order' => 'created_at.desc', 'limit' => 15]);
$current = $history[0]['capital_eur'] ?? null;
?>
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>SAPTA — Capitale</title>
    <link rel="stylesheet" href="assets/style.css">
</head>
<body>

<header class="hero compact">
    <div class="hero-top">
        <div>
            <div class="eyebrow">SAPTA v5.1.1</div>
            <h1>Capitale operativo</h1>
            <p>Il capitale usato da Modulo E per il dimensionamento delle posizioni.</p>
        </div>
        <a class="back-link" href="index.php">← Dashboard</a>
    </div>
</header>

<div class="stat-grid">
    <div class="stat-card">
        <div class="stat-label">Capitale corrente</div>
        <div class="stat-value"><?= $current !== null ? fmt_eur($current) : 'Non impostato' ?></div>
    </div>
</div>

<?php render_nav('capital.php'); ?>

<div class="wrap">

<?php if ($message): ?>
<div class="flash-msg<?= $message_error ? ' error' : '' ?>" style="margin-bottom:22px;"><?= e($message) ?></div>
<?php endif; ?>

<section>
    <h2>Aggiorna capitale</h2>
    <form method="POST" class="form-grid">
        <div class="field"><label>Nuovo capitale (€)</label><input type="text" name="capital_eur" required></div>
        <div class="field"><label>Tipo</label>
            <select name="change_type">
                <option value="manual_set">Impostazione manuale</option>
                <option value="deposit">Deposito</option>
                <option value="withdrawal">Prelievo</option>
            </select>
        </div>
        <div class="field" style="grid-column: 1 / -1;"><label>Nota (opzionale)</label><input type="text" name="note" placeholder="es. inizio nuovo test"></div>
        <div><button type="submit">Aggiorna</button></div>
    </form>
</section>

<section>
    <div class="section-head"><h2>Storico modifiche</h2></div>
    <div class="table-wrap">
    <table>
        <thead><tr><th>Data</th><th>Capitale</th><th>Tipo</th><th>Nota</th></tr></thead>
        <tbody>
        <?php if (empty($history)): ?><tr><td colspan="4" class="empty-state">Nessuno storico disponibile.</td></tr><?php endif; ?>
        <?php foreach ($history as $h): ?>
        <tr>
            <td><?= e(date('d/m/Y H:i', strtotime($h['created_at']))) ?></td>
            <td><?= fmt_eur($h['capital_eur']) ?></td>
            <td><?= e($h['change_type']) ?></td>
            <td class="muted"><?= e($h['note'] ?? '') ?></td>
        </tr>
        <?php endforeach; ?>
        </tbody>
    </table>
    </div>
</section>

</div>

<footer>SAPTA · Capitale · Pagina generata <?= date('d/m/Y H:i') ?></footer>
</body>
</html>
