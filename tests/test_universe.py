import universe as U


def test_bpso_rimosso_e_universo_coerente():
    full = U.UNIVERSE_FULL
    assert 'BPSO.MI' not in full and 'BPSO.MI' not in U.UNIVERSE_IT
    assert len(full) == len(set(full)) == 134
    assert len(U.UNIVERSE_USA) == 98 and len(U.UNIVERSE_IT) == 36
    meta = U.get_universe_metadata()
    assert set(meta) == set(full) and all(m['liquidity_bucket'] in (U.LIQ_HIGH, U.LIQ_MEDIUM, U.LIQ_LOW) for m in meta.values())
