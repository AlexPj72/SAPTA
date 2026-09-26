<?php
session_start();
require_once 'config.php';
require_once 'helpers.php';

if (!isset($_SESSION['chat_history'])) {
    $_SESSION['chat_history'] = [];
}

$error = null;

if ($_SERVER['REQUEST_METHOD'] === 'POST' && ($_POST['action'] ?? '') === 'reset') {
    $_SESSION['chat_history'] = [];
}

if ($_SERVER['REQUEST_METHOD'] === 'POST' && ($_POST['action'] ?? '') === 'send') {
    $message = trim($_POST['message'] ?? '');
    if ($message !== '') {
        if (empty($_SESSION['chat_history'])) {
            // Primo messaggio della conversazione: precede il contesto reale
            // come "system" (Gemini non ha un ruolo system dedicato in questo
            // formato semplice, quindi lo passiamo come primo turno "user"
            // seguito da un ack del modello, poi la vera domanda).
            $_SESSION['chat_history'][] = ['role' => 'user', 'text' => build_chat_context()];
            $_SESSION['chat_history'][] = ['role' => 'model', 'text' => 'Ok, ho il contesto. Fai pure la tua domanda.'];
        }
        $_SESSION['chat_history'][] = ['role' => 'user', 'text' => $message];

        // Limita la storia inviata (contesto + ultimi 12 turni) per non far
        // crescere indefinitamente il prompt in conversazioni lunghe.
        $to_send = array_slice($_SESSION['chat_history'], 0, 2);
        $to_send = array_merge($to_send, array_slice($_SESSION['chat_history'], -12));

        $reply = gemini_chat_with_tools($to_send);
        if ($reply === null) {
            $error = (GEMINI_CHAT_API_KEY || GEMINI_API_KEY)
                ? "La Chat AI non ha risposto (errore di rete o quota Gemini esaurita). Riprova tra poco."
                : "Chat AI non configurata: manca la chiave Gemini in config.php (GEMINI_API_KEY o GEMINI_CHAT_API_KEY).";
            array_pop($_SESSION['chat_history']); // non teniamo il messaggio senza risposta
        } else {
            $_SESSION['chat_history'][] = ['role' => 'model', 'text' => $reply];
        }
    }
}

// Per la visualizzazione, saltiamo i primi due turni "di contesto" (non sono
// una domanda dell'utente, servirebbero solo a confondere la lettura).
$visible_history = count($_SESSION['chat_history']) > 2 ? array_slice($_SESSION['chat_history'], 2) : [];
?>
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>SAPTA — Chat AI</title>
    <link rel="icon" href="assets/favicon.svg">
    <link rel="stylesheet" href="assets/style.css">
    <style>
        .chat-box { display: flex; flex-direction: column; gap: 12px; max-height: 55vh; overflow-y: auto; padding: 4px 2px 10px; }
        .chat-msg { max-width: 78%; padding: 11px 15px; border-radius: 14px; font-size: 14px; line-height: 1.5; white-space: pre-wrap; }
        .chat-msg.user { align-self: flex-end; background: var(--brand); color: #fff; border-bottom-right-radius: 4px; }
        .chat-msg.model { align-self: flex-start; background: var(--surface-alt); border: 1px solid var(--border); border-bottom-left-radius: 4px; }
        .chat-form { display: flex; gap: 10px; margin-top: 16px; }
        .chat-form textarea { flex: 1; resize: none; min-height: 46px; }
    </style>
</head>
<body>

<header class="hero compact">
    <div class="hero-top">
        <div>
            <div class="eyebrow">SAPTA v5.1.1</div>
            <h1>Chat AI</h1>
            <p>Fai domande su un titolo, sui movimenti di oggi, sul radar anomalie o sul rischio — l'analista recupera i dati veri quando servono, non risponde a memoria.</p>
        </div>
        <a class="back-link" href="index.php">← Dashboard</a>
    </div>
</header>

<?php render_nav('chat.php'); ?>

<div class="wrap">

<?php if ($error): ?>
<div class="flash-msg error" style="margin-bottom:18px;"><?= e($error) ?></div>
<?php endif; ?>

<section>
    <div class="section-head">
        <div><h2>Conversazione</h2><p class="muted">Il contesto (briefing, segnali, capitale) viene ricaricato ad ogni nuova conversazione.</p></div>
        <form method="POST"><input type="hidden" name="action" value="reset"><button type="submit" class="btn-secondary">Nuova conversazione</button></form>
    </div>

    <div class="chat-box">
        <?php if (empty($visible_history)): ?>
            <p class="muted">Nessun messaggio ancora. Prova a chiedere, ad esempio: "quali titoli si muovono di più oggi?", "dammi il dettaglio di MELI" oppure "cosa ha rilevato il radar anomalie oggi?".</p>
        <?php endif; ?>
        <?php foreach ($visible_history as $m): ?>
            <div class="chat-msg <?= e($m['role']) ?>"><?= nl2br(e($m['text'])) ?></div>
        <?php endforeach; ?>
    </div>

    <form method="POST" class="chat-form">
        <input type="hidden" name="action" value="send">
        <textarea name="message" placeholder="Scrivi qui la tua domanda..." required></textarea>
        <button type="submit">Invia</button>
    </form>
</section>

</div>

<footer>SAPTA · Chat AI · Pagina generata <?= date('d/m/Y H:i') ?></footer>
</body>
</html>
