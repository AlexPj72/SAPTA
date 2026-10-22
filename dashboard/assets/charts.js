/**
 * SAPTA — funzioni condivise per i grafici Chart.js (estratte da grafico.php
 * il 19/09 per essere riusate anche in valuta.php senza duplicare codice).
 * Richiede Chart.js già caricato (assets/chart.umd.min.js) PRIMA di questo file.
 */
// Guardia: se Chart.js non si è caricato, evita che il resto del file
// fallisca con un ReferenceError (che impedirebbe anche a showChartErrors
// di essere definita, lasciando la pagina senza alcun avviso visibile).
if (typeof Chart !== 'undefined') {
    Chart.defaults.font.family = "'Inter', sans-serif";
    Chart.defaults.color = '#6b7280';
}

// [FIX 30/09 - handoff Codex] Prima maximumFractionDigits:0 -> titoli da pochi euro
// (4,25 / 4,50) mostravano solo interi. Simbolo valuta da window.SAPTA_CURRENCY (default €).
function currencySymbol() { return window.SAPTA_CURRENCY || '€'; }
function priceDecimals(value) { return Math.abs(value) >= 1000 ? 0 : 2; }
function eurTick(value) { const d = priceDecimals(value); return currencySymbol() + value.toLocaleString('it-IT', {minimumFractionDigits: d, maximumFractionDigits: d}); }
function pctTick(value) { return value.toLocaleString('it-IT', {maximumFractionDigits: 0}) + '%'; }

// Mostra al massimo ~10 etichette sull'asse X per non affollarlo
function sparseTicks(labels) {
    const step = Math.max(1, Math.ceil(labels.length / 10));
    return { callback: (val, idx) => (idx % step === 0 ? labels[idx] : '') };
}

function buildChart(canvasId, labels, values, lineColor, fillColor, seriesLabel, target, invalidation, unit, pos) {
    if (typeof Chart === 'undefined') return;
    unit = unit || 'eur'; // 'eur' (default, retrocompatibile) oppure 'pct'
    const tickFn = unit === 'pct' ? pctTick : eurTick;
    const fmtValue = (v) => unit === 'pct'
        ? v.toLocaleString('it-IT', {minimumFractionDigits: 1, maximumFractionDigits: 1}) + '%'
        : currencySymbol() + v.toLocaleString('it-IT', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    const el = document.getElementById(canvasId);
    if (!el || !values.length) return;

    const datasets = [{
        label: seriesLabel,
        data: values,
        borderColor: lineColor,
        backgroundColor: fillColor,
        fill: true,
        tension: 0.25,
        pointRadius: 0,
        pointHoverRadius: 5,
        pointHoverBackgroundColor: lineColor,
        borderWidth: 2.5,
    }];
    // Posizione in portafoglio: punti oltre target / sotto stop evidenziati
    if (pos) {
        const col = [], rad = [];
        values.forEach(v => {
            const up = target !== null && v >= target, dn = invalidation !== null && v <= invalidation;
            col.push(up ? '#16a34a' : (dn ? '#dc2626' : lineColor));
            rad.push(up || dn ? 5 : 0);
        });
        datasets[0].pointBackgroundColor = col;
        datasets[0].pointBorderColor = col;
        datasets[0].pointRadius = rad;
        datasets.push({
            label: 'Acquisto', data: labels.map(() => pos.entry),
            borderColor: '#2563eb', borderDash: [2, 3], borderWidth: 1.5, pointRadius: 0, fill: false,
        });
    }

    if (target !== null) {
        datasets.push({
            label: 'Target', data: labels.map(() => target),
            borderColor: '#16a34a', borderDash: [6, 4], borderWidth: 1.5, pointRadius: 0, fill: false,
        });
    }
    if (invalidation !== null) {
        datasets.push({
            label: pos ? 'Stop inferiore' : 'Invalidazione', data: labels.map(() => invalidation),
            borderColor: '#dc2626', borderDash: [6, 4], borderWidth: 1.5, pointRadius: 0, fill: false,
        });
    }

    new Chart(el, {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#1c2333', padding: 10, titleFont: { weight: '700' },
                    callbacks: {
                        label: (ctx) => ctx.dataset.label + ': ' + fmtValue(ctx.parsed.y),
                        afterBody: (items) => {
                            if (!pos || !items.length) return [];
                            const v = items[0].parsed.y;
                            const eur = (v - pos.entry) * pos.qty * pos.fx;
                            const pct = (v / pos.entry - 1) * 100;
                            const f = (x, d) => x.toLocaleString('it-IT', {minimumFractionDigits: d, maximumFractionDigits: d, signDisplay: 'always'});
                            const out = ['Rispetto all\'acquisto: ' + f(eur, 2) + ' € (' + f(pct, 2) + '%)'];
                            if (target !== null && v >= target) out.push('▲ Oltre il target atteso');
                            if (invalidation !== null && v <= invalidation) out.push('▼ Sotto lo stop');
                            return out;
                        }
                    }
                }
            },
            scales: {
                x: { grid: { display: false }, ticks: sparseTicks(labels) },
                y: { grid: { color: '#eef0f5' }, ticks: { callback: tickFn }, title: { display: true, text: unit === 'pct' ? 'Percentuale' : 'Prezzo (' + (currencySymbol() === '$' ? 'USD' : 'EUR') + ')' } }
            }
        }
    });
}

/** Mostra gli avvisi di errore se Chart.js non è disponibile - chiamare
 * subito dopo aver verificato `typeof Chart === 'undefined'`. */
function showChartErrors(ids) {
    ids.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.style.display = 'block';
    });
}


/** Grafico di una posizione di portafoglio: prezzo in € (2 decimali) da almeno 7 giorni prima
 *  dell'acquisto fino alla vendita (o a oggi se aperta). Linee: acquisto viola, target verde,
 *  invalidazione rossa. Punti verdi/rossi dove il prezzo supera il target o scende sotto lo stop.
 *  cfg = {labels, values, entry, target, stop, qty, buyIdx, sellIdx} (valori già in €). */
function buildPositionChart(canvasId, cfg) {
    if (typeof Chart === 'undefined') return;
    const el = document.getElementById(canvasId);
    if (!el || !cfg.values.length) return;
    const eur = (v) => v.toLocaleString('it-IT', {minimumFractionDigits: 2, maximumFractionDigits: 2}) + ' €';
    const sgn = (v, d) => v.toLocaleString('it-IT', {minimumFractionDigits: d, maximumFractionDigits: d, signDisplay: 'always'});
    const n = cfg.values.length, line = (v) => cfg.labels.map(() => v);
    const col = [], rad = [];
    cfg.values.forEach((v, i) => {
        const up = cfg.target !== null && v >= cfg.target, dn = cfg.stop !== null && v <= cfg.stop;
        const isBuy = i === cfg.buyIdx, isSell = i === cfg.sellIdx;
        col.push(isBuy ? '#7c3aed' : (isSell ? '#111827' : (up ? '#16a34a' : (dn ? '#dc2626' : '#2563eb'))));
        rad.push(isBuy || isSell ? 7 : (up || dn ? 4 : 0));
    });
    const datasets = [{
        label: 'Prezzo', data: cfg.values, borderColor: '#2563eb', backgroundColor: 'rgba(37,99,235,0.06)', fill: true,
        tension: 0.2, borderWidth: 2, pointRadius: rad, pointBackgroundColor: col, pointBorderColor: col, pointHoverRadius: 5,
    }, {
        label: 'Acquisto', data: line(cfg.entry), borderColor: '#7c3aed', borderWidth: 1.8, borderDash: [4, 3], pointRadius: 0, fill: false,
    }];
    if (cfg.target !== null) datasets.push({label: 'Target da raggiungere', data: line(cfg.target), borderColor: '#16a34a', borderWidth: 1.5, borderDash: [6, 4], pointRadius: 0, fill: false});
    if (cfg.stop !== null) datasets.push({label: 'Invalidazione', data: line(cfg.stop), borderColor: '#dc2626', borderWidth: 1.5, borderDash: [6, 4], pointRadius: 0, fill: false});
    new Chart(el, {
        type: 'line', data: {labels: cfg.labels, datasets},
        options: {
            responsive: true, maintainAspectRatio: false, interaction: {mode: 'index', intersect: false},
            plugins: {
                legend: {display: false},
                tooltip: {
                    backgroundColor: '#1c2333', padding: 10,
                    callbacks: {
                        label: (c) => c.dataset.label + ': ' + eur(c.parsed.y),
                        afterBody: (items) => {
                            const i = items[0].dataIndex, v = items[0].parsed.y, out = [];
                            if (i === cfg.buyIdx) out.push('● ACQUISTO');
                            if (i === cfg.sellIdx) out.push('● VENDITA');
                            if (i >= cfg.buyIdx && cfg.buyIdx >= 0) out.push('Rispetto all\'acquisto: ' + sgn((v - cfg.entry) * cfg.qty, 2) + ' € (' + sgn((v / cfg.entry - 1) * 100, 2) + '%)');
                            if (cfg.target !== null && v >= cfg.target) out.push('▲ Oltre il target');
                            if (cfg.stop !== null && v <= cfg.stop) out.push('▼ Sotto l\'invalidazione');
                            return out;
                        }
                    }
                }
            },
            scales: {
                x: {grid: {display: false}, ticks: sparseTicks(cfg.labels)},
                y: {grid: {color: '#eef0f5'}, ticks: {callback: (v) => v.toLocaleString('it-IT', {minimumFractionDigits: 2, maximumFractionDigits: 2}) + ' €'}, title: {display: true, text: 'Prezzo (€)'}}
            }
        }
    });
}
