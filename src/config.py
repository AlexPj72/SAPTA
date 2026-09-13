import os
from supabase import create_client, Client

# Configurazione Supabase
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing Supabase credentials in environment variables")

# Client Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Configurazione API esterne
FINNHUB_KEY = os.environ.get('FINNHUB_KEY', '')
NEWSAPI_KEY = os.environ.get('NEWSAPI_KEY', '')
HUGGINGFACE_API_KEY = os.environ.get('HUGGINGFACE_API_KEY', '')  # (v3.1) sentiment via Inference API
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')  # (Modulo I) ragionamento LLM indipendente, free tier Google AI Studio

# Ticker da monitorare (personalizza), divisi per mercato (v3.5 — necessario per il run
# dedicato post-chiusura USA, vedi SAPTA_v3.md §1.6bis)
TICKERS_USA = ["AAPL", "MSFT", "GOOGL"]
TICKERS_EU = ["ENI.MI", "ISP.MI", "UCG.MI"]
TICKERS = TICKERS_USA + TICKERS_EU  # lista completa, usata di default (--market=ALL)

# Soglie di riconciliazione multi-fonte
PRICE_DIVERGENCE_THRESHOLD = 0.003  # 0.3%

# Soglie Modulo H (anomalie)
VOLUME_ANOMALY_THRESHOLD = 5.0  # 5x la media
PRICE_ANOMALY_THRESHOLD = 0.03  # 3%

# (v3.1) Cache news: minuti entro cui le news di un ticker vengono riusate
# invece di richiamare NewsAPI, per restare sotto il limite di 100 richieste/giorno free tier
NEWS_CACHE_MINUTES = 60

# (v3.2) Mappa settore per ticker, usata dal Modulo E per il limite di concentrazione.
# Personalizza in base alla tua watchlist reale (TICKERS sopra).
SECTOR_MAP = {
    "AAPL": "Tech",
    "MSFT": "Tech",
    "GOOGL": "Tech",
    "ENI.MI": "Energy",
    "ISP.MI": "Banks",
    "UCG.MI": "Banks",
}

# (v3.2) Limite di concentrazione settoriale nel Modulo E: numero massimo di segnali BUY
# approvati per lo stesso settore entro la finestra sotto, prima di declassare a HOLD
# per "concentrazione" anche se il singolo segnale supererebbe il filtro costo/rendimento.
MAX_POSITIONS_PER_SECTOR = 2
SECTOR_EXPOSURE_LOOKBACK_DAYS = 10  # finestra approssimativa di detenzione swing trading

# (v3.2) Protezione Pattern Day Trader — rilevante solo con broker Alpaca e capitale < $25.000.
# Placeholder di configurazione: la logica vera e propria arriva con il Modulo G (Fase 7),
# quando il sistema traccia le esecuzioni reali e può contare i day-trade effettivi.
PDT_PROTECTION_ENABLED = True
PDT_MAX_DAY_TRADES_5_DAYS = 3
PDT_ACCOUNT_THRESHOLD_USD = 25000
