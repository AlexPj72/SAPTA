<?php
require_once 'config.php';
require_once 'helpers.php';

// Prende il briefing più recente disponibile (di solito oggi, ma se il
// workflow non è ancora girato - es. festivo, weekend, primo giorno -
// mostra l'ultimo generato con la data ben visibile, invece di una pagina vuota).
$latest_date_rows = supabase_query('daily_briefing', ['select' => 'briefing_date', 'order' => 'briefing_date.desc', 'limit' => 1]);
$briefing_date = $latest_date_rows[0]['briefing_date'] ?? null;
$briefing = $briefing_date
    ? supabase_query('daily_briefing', ['select' => '*', 'briefing_date' => 'eq.' . $briefing_date, 'order' => 'rank.asc'])
    : [];
$is_today = $briefing_date === date('Y-m-d');
?>
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>SAPTA — Briefing pre-apertura</title>
    <link rel="stylesheet" href="assets/style.css">
</head>
<body>

<header class="hero compact">
    <div class="hero-top">
        <div>
            <div class="eyebrow">SAPTA v5.1.1</div>
            <h1>Briefing pre-apertura</h1>
            <p>Shortlist generata da AI prima dell'apertura, su trend recente, settore, contesto macro/GDELT ed earnings.</p>
        </div>
        <a class="back-link" href="index.php">← Dashboard</a>
    </div>
</header>

<?php render_nav('briefing.php'); ?>

<div class="wrap">

<section>
    <div class="explain" style="max-width:none; background:var(--amber-bg); border-color:#fde3ad; color:#92400e;">
        <b>Non è una previsione di prezzo.</b> È un'ipotesi qualitativa ragionata da un modello linguistico su dati reali (trend, settore, tono GDELT, earnings, titoli macro del giorno) — nello stile di una nota mattutina di un analista, non validata da backtest. Decidi sempre con la tua testa, non seguirla alla cieca.
    </div>
</section>

<section>
    <div class="section-head">
        <div>
            <h2><?= $briefing_date ? e(date('d/m/Y', strtotime($briefing_date))) : 'Nessun briefing disponibile' ?></h2>
            <p class="muted"><?= $is_today ? "Briefing di oggi" : ($briefing_date ? "⚠️ Non è ancora stato generato quello di oggi — questo è l'ultimo disponibile" : "Il primo briefing verrà generato alla prossima esecuzione programmata (06:00 UTC, giorni feriali)") ?></p>
        </div>
    </div>

    <?php if (empty($briefing)): ?>
        <p class="empty-state">Nessun dato ancora disponibile.</p>
    <?php else: ?>
    <div class="table-wrap">
    <table>
        <thead><tr><th>#</th><th>Ticker</th><th>Motivazione</th><th>Var. 1gg</th><th>Var. 5gg</th><th>Contesto paese</th><th>Earnings</th></tr></thead>
        <tbody>
        <?php foreach ($briefing as $b): ?>
        <tr>
            <td><?= (int) $b['rank'] ?></td>
            <td><a class="ticker-link" href="grafico.php?ticker=<?= urlencode($b['ticker']) ?>"><?= e($b['ticker']) ?></a></td>
            <td style="white-space:normal; max-width:420px;"><?= e($b['motivazione']) ?></td>
            <td class="<?= ($b['chg_1d'] ?? 0) >= 0 ? 'positive' : 'negative' ?>"><?= $b['chg_1d'] !== null ? (($b['chg_1d'] >= 0 ? '+' : '') . number_format($b['chg_1d'], 2) . '%') : '—' ?></td>
            <td class="<?= ($b['chg_5d'] ?? 0) >= 0 ? 'positive' : 'negative' ?>"><?= $b['chg_5d'] !== null ? (($b['chg_5d'] >= 0 ? '+' : '') . number_format($b['chg_5d'], 2) . '%') : '—' ?></td>
            <td><?= isset($b['gdelt_tone']) ? number_format($b['gdelt_tone'], 2) : '—' ?></td>
            <td><?= !empty($b['has_earnings']) ? '<span class="badge warn">sì</span>' : '<span class="muted">no</span>' ?></td>
        </tr>
        <?php endforeach; ?>
        </tbody>
    </table>
    </div>
    <?php endif; ?>
</section>

<section>
    <h2>Vuoi discuterne?</h2>
    <p class="muted">Apri la <a href="chat.php">Chat AI</a> per fare domande su questi titoli o sui segnali attivi, con lo stesso contesto sotto mano.</p>
    <a class="btn" href="chat.php">Vai alla Chat AI →</a>
</section>

</div>

<footer>SAPTA · Briefing · Pagina generata <?= date('d/m/Y H:i') ?></footer>
</body>
</html>
