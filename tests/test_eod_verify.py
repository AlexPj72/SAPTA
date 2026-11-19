import modulo_eod_verify as V


def h(t, entry=10.0):
    return {'ticker': t, 'entry_price': entry}


def test_ipotesi_in_attesa_e_non_verificabili():
    closes = {'ENI.MI': 10.0, 'ISP.MI': 3.0}                                   # il mercato EU ha la chiusura, gli USA no
    hyp = [h('ENI.MI'), h('TEN.MI'), h('AAPL'), h('MSFT'), h('G.MI', entry=None)]
    r = V.classify_missing(hyp, closes, '2026-11-18')
    assert r['in_attesa'] == ['AAPL', 'MSFT']                                  # USA: chiusura giornaliera non ancora caricata
    assert r['non_verificabili'] == ['TEN.MI', 'G.MI']                         # EU: il mercato c'e' ma non questo ticker / manca l'entry


def test_tutte_con_chiusura_nessuna_mancante():
    r = V.classify_missing([h('AAPL'), h('ENI.MI')], {'AAPL': 1.0, 'ENI.MI': 2.0}, '2026-11-18')
    assert r == {'in_attesa': [], 'non_verificabili': []}


def test_indici_sono_classificati_per_mercato():
    r = V.classify_missing([h('^GSPC'), h('FTSEMIB.MI')], {'AAPL': 1.0}, '2026-11-18')
    assert r['non_verificabili'] == ['^GSPC'] and r['in_attesa'] == ['FTSEMIB.MI']
