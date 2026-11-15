import os, sys, types

SRC = os.path.join(os.path.dirname(__file__), '..', 'src')
sys.path.insert(0, os.path.abspath(SRC))
sys.path.insert(0, os.path.dirname(__file__))

from fakes import FakeSupabase  # noqa: E402

# 'config' crea un client Supabase reale all'import: lo sostituiamo con un doppione, cosi' i test non toccano nulla.
_cfg = types.ModuleType('config')
_cfg.supabase = FakeSupabase()
_cfg.FINNHUB_KEY = ''
_cfg.PRICE_DIVERGENCE_THRESHOLD = 0.003
_cfg.GEMINI_API_KEY = ''
sys.modules['config'] = _cfg
if 'yfinance' not in sys.modules:
    try:
        import yfinance  # noqa: F401
    except ImportError:
        sys.modules['yfinance'] = types.ModuleType('yfinance')
