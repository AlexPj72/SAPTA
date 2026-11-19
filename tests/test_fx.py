"""fx_rates: tassi BCE EUR/USD, giorni festivi, weekend, dati mancanti, un solo tasso per giornata."""
from datetime import date, datetime, timedelta, timezone

import pytest

import fx
import load_fx_rates as LF
from fakes import FakeSupabase

U = timezone.utc

ECB_XML = """<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01" xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <gesmes:subject>Reference rates</gesmes:subject>
  <gesmes:Sender><gesmes:name>European Central Bank</gesmes:name></gesmes:Sender>
  <Cube>
    <Cube time="2026-11-18"><Cube currency="USD" rate="1.1650"/><Cube currency="JPY" rate="180.10"/></Cube>
    <Cube time="2026-11-17"><Cube currency="USD" rate="1.1600"/><Cube currency="JPY" rate="179.80"/></Cube>
    <Cube time="2026-11-16"><Cube currency="USD" rate="1.1550"/></Cube>
    <Cube time="2026-11-13"><Cube currency="USD" rate="1.1500"/></Cube>
  </Cube>
</gesmes:Envelope>"""


class _Q:
    def __init__(self, rows): self.rows, self.ref, self.fail = rows, None, False
    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def lt(self, col, v): self.ref = v; return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def execute(self):
        class R: pass
        r = R()
        r.data = sorted([x for x in self.rows if x['rate_date'] < self.ref], key=lambda x: x['rate_date'], reverse=True)[:1]
        return r


class _DB:
    def __init__(self, rates): self.rows = [{'rate_date': d, 'rate': v, 'source': 'ECB'} for d, v in rates.items()]
    def table(self, name): return _Q(self.rows)


class _Boom:
    def table(self, n): raise RuntimeError('db giu')


RATES = {'2026-11-13': 1.15, '2026-11-16': 1.155, '2026-11-17': 1.16, '2026-11-18': 1.165}


# ---------------------------------------------------------------- parsing BCE
def test_parse_xml_bce():
    r = fx.parse_ecb_xml(ECB_XML)
    assert r == {date(2026, 11, 18): 1.165, date(2026, 11, 17): 1.16, date(2026, 11, 16): 1.155, date(2026, 11, 13): 1.15}
    assert fx.parse_ecb_xml(ECB_XML, 'JPY') == {date(2026, 11, 18): 180.10, date(2026, 11, 17): 179.80}


def test_parse_xml_non_valido_o_non_plausibile():
    with pytest.raises(ValueError):
        fx.parse_ecb_xml('<non xml')
    with pytest.raises(ValueError):
        fx.parse_ecb_xml(ECB_XML.replace('1.1650', '11.65'))                     # tasso non plausibile
    with pytest.raises(ValueError):
        fx.parse_ecb_xml(ECB_XML.replace('2026-11-18', '18/11/2026'))


# ---------------------------------------------------------------- regola della data
def test_tasso_in_vigore_e_l_ultimo_strettamente_precedente():
    db = _DB(RATES)
    r = fx.rate_for_date(db, date(2026, 11, 18))
    assert r.rate_date == date(2026, 11, 17) and r.rate == 1.16 and r.eur_per_unit == pytest.approx(1 / 1.16)


def test_weekend_e_lunedi_usano_il_tasso_di_venerdi():
    db = _DB(RATES)
    for d in (date(2026, 11, 14), date(2026, 11, 15), date(2026, 11, 16)):           # sabato, domenica, lunedi'
        assert fx.rate_for_date(db, d).rate_date == date(2026, 11, 13)


def test_giorni_festivi_target_usano_l_ultimo_lavorativo():
    db = _DB({'2026-12-23': 1.17, '2026-12-24': 1.171, '2026-12-28': 1.172})        # BCE chiusa 25-26/12
    assert fx.rate_for_date(db, date(2026, 12, 25)).rate_date == date(2026, 12, 24)
    assert fx.rate_for_date(db, date(2026, 12, 28)).rate_date == date(2026, 12, 24)
    assert fx.rate_for_date(db, date(2026, 12, 29)).rate_date == date(2026, 12, 28)
    db = _DB({'2026-12-31': 1.18, '2027-01-04': 1.181})                              # 1/1 chiuso
    assert fx.rate_for_date(db, date(2027, 1, 2)).rate_date == date(2026, 12, 31)


def test_la_stessa_data_da_sempre_la_stessa_riga_anche_dopo_la_pubblicazione_del_giorno():
    """E (mattina) e T (sera) dello stesso giorno: la BCE pubblica il tasso del 18 alle 16:00 ma per il 18 conta quello del 17."""
    rates = {'2026-11-17': 1.16}
    mattina = fx.rate_for_date(_DB(rates), date(2026, 11, 18))
    rates['2026-11-18'] = 1.165                                                      # pubblicato nel pomeriggio
    sera = fx.rate_for_date(_DB(rates), date(2026, 11, 18))
    assert mattina == sera and sera.rate_date == date(2026, 11, 17)


def test_data_di_riferimento_dal_timestamp_del_segnale():
    assert fx.reference_date('2026-11-18T09:30:00+00:00') == date(2026, 11, 18)
    assert fx.reference_date('2026-11-18T23:30:00.12345+00:00') == date(2026, 11, 18)
    assert fx.reference_date(datetime(2026, 11, 18, 23, 59, tzinfo=U)) == date(2026, 11, 18)
    assert fx.reference_date(datetime(2026, 11, 19, 1, 0, tzinfo=timezone(timedelta(hours=2)))) == date(2026, 11, 18)


# ---------------------------------------------------------------- dati mancanti: errore esplicito, nessun ripiego
def test_tabella_vuota_o_nessun_tasso_precedente():
    with pytest.raises(fx.FxRateUnavailable):
        fx.rate_for_date(_DB({}), date(2026, 11, 18))
    with pytest.raises(fx.FxRateUnavailable):
        fx.rate_for_date(_DB({'2026-11-18': 1.16}), date(2026, 11, 18))              # esiste solo il tasso del giorno stesso


def test_tasso_troppo_vecchio():
    with pytest.raises(fx.FxRateUnavailable, match='piu\' vecchio'):
        fx.rate_for_date(_DB({'2026-11-01': 1.16}), date(2026, 11, 18))
    assert fx.rate_for_date(_DB({'2026-11-11': 1.16}), date(2026, 11, 18)).rate_date == date(2026, 11, 11)      # 7 giorni: ancora valido


def test_errore_database_e_tasso_non_valido():
    with pytest.raises(fx.FxRateUnavailable):
        fx.rate_for_date(_Boom(), date(2026, 11, 18))
    with pytest.raises(fx.FxRateUnavailable):
        fx.rate_for_date(_DB({'2026-11-17': 0.0}), date(2026, 11, 18))
    with pytest.raises(fx.FxRateUnavailable):
        fx.rate_for_date(_DB({'2026-11-17': 99.0}), date(2026, 11, 18))


def test_nessun_riferimento_a_yahoo_nel_modulo_fx():
    import inspect
    src = inspect.getsource(fx) + inspect.getsource(LF)
    assert 'yfinance' not in src and 'EURUSD=X' not in src and 'import yf' not in src and 'yf.' not in src


# ---------------------------------------------------------------- loader BCE
def test_loader_inserisce_e_non_modifica_i_tassi_esistenti():
    db = FakeSupabase()
    # il fake usa la chiave di on_conflict: la riga esistente non deve cambiare
    k = ('EUR', 'USD', '2026-11-17')
    class FX(FakeSupabase):
        def table(self, name):
            q = super().table(name)
            orig = q.execute
            def ex():
                if q.mode == 'upsert':
                    cols = q.kw['on_conflict'].split(',')
                    ins = []
                    for r in q.payload:
                        key = tuple(r[c] for c in cols)
                        if key in self.prezzi:
                            continue
                        self.prezzi[key] = dict(r); ins.append(r)
                    class R: data = ins
                    return R()
                return orig()
            q.execute = ex
            return q
    db = FX()
    db.prezzi[k] = {'rate': 9.999}
    assert LF.run(db, fetcher=lambda url: ECB_XML) == 0
    assert len(db.prezzi) == 4 and db.prezzi[k] == {'rate': 9.999}                    # esistente intatta
    assert LF.run(db, fetcher=lambda url: ECB_XML) == 0 and len(db.prezzi) == 4       # idempotente


def test_loader_errori_producono_exit_code_1():
    assert LF.run(FakeSupabase(), fetcher=lambda url: (_ for _ in ()).throw(RuntimeError('rete'))) == 1
    assert LF.run(FakeSupabase(), fetcher=lambda url: '<Envelope/>') == 1              # nessun tasso
    assert LF.run(FakeSupabase(), fetcher=lambda url: 'xml rotto') == 1
    db = FakeSupabase(); db.fail_writes = True
    assert LF.run(db, fetcher=lambda url: ECB_XML) == 1


def test_loader_usa_gli_url_bce():
    seen = []
    LF.run(FakeSupabase(), fetcher=lambda url: seen.append(url) or ECB_XML)
    LF.run(FakeSupabase(), fetcher=lambda url: seen.append(url) or ECB_XML, hist90=True)
    assert seen == [fx.ECB_DAILY_URL, fx.ECB_HIST_90D_URL] and all('ecb.europa.eu' in u for u in seen)
