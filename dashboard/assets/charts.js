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

function eurTick(value) { return '€' + value.toLocaleString('it-IT', {maximumFractionDigits: 0}); }
function pctTick(value) { return value.toLocaleString('it-IT', {maximumFractionDigits: 0}) + '%'; }

// Mostra al massimo ~10 etichette sull'asse X per non affollarlo
function sparseTicks(labels) {
    const step = Math.max(1, Math.ceil(labels.length / 10));
    return { callback: (val, idx) => (idx % step === 0 ? labels[idx] : '') };
}

function buildChart(canvasId, labels, values, lineColor, fillColor, seriesLabel, target, invalidation, unit) {
    if (typeof Chart === 'undefined') return;
    unit = unit || 'eur'; // 'eur' (default, retrocompatibile) oppure 'pct'
    const tickFn = unit === 'pct' ? pctTick : eurTick;
    const fmtValue = (v) => unit === 'pct'
        ? v.toLocaleString('it-IT', {minimumFractionDigits: 1, maximumFractionDigits: 1}) + '%'
        : '€' + v.toLocaleString('it-IT', {minimumFractionDigits: 2, maximumFractionDigits: 2});
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

    if (target !== null) {
        datasets.push({
            label: 'Target', data: labels.map(() => target),
            borderColor: '#16a34a', borderDash: [6, 4], borderWidth: 1.5, pointRadius: 0, fill: false,
        });
    }
    if (invalidation !== null) {
        datasets.push({
            label: 'Invalidazione', data: labels.map(() => invalidation),
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
                        label: (ctx) => ctx.dataset.label + ': ' + fmtValue(ctx.parsed.y)
                    }
                }
            },
            scales: {
                x: { grid: { display: false }, ticks: sparseTicks(labels) },
                y: { grid: { color: '#eef0f5' }, ticks: { callback: tickFn }, title: { display: true, text: unit === 'pct' ? 'Percentuale' : 'Prezzo (EUR/USD)' } }
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
