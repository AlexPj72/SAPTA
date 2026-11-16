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
_cfg.NEWSAPI_KEY = ''
_cfg.HUGGINGFACE_API_KEY = ''
_cfg.NEWS_CACHE_MINUTES = 60
sys.modules['config'] = _cfg
if 'yfinance' not in sys.modules:
    try:
        import yfinance  # noqa: F401
    except ImportError:
        sys.modules['yfinance'] = types.ModuleType('yfinance')

# librerie pesanti non necessarie ai test (indicatori, LLM): sostituite da moduli vuoti se non installate
for _name in ('pandas_ta_classic', 'pandas_ta', 'google', 'google.genai', 'google.generativeai'):
    if _name not in sys.modules:
        try:
            __import__(_name)
        except ImportError:
            sys.modules[_name] = types.ModuleType(_name)
