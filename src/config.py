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
        HUGGINGFACE_API_KEY = os.environ.get('HUGGINGFACE_API_KEY', '')

        # Ticker da monitorare
        TICKERS_USA = ["AAPL", "MSFT", "GOOGL"]
        TICKERS_EU = ["ENI.MI", "ISP.MI", "UCG.MI"]
        TICKERS = TICKERS_USA + TICKERS_EU

        # Soglie
        PRICE_DIVERGENCE_THRESHOLD = 0.003
        VOLUME_ANOMALY_THRESHOLD = 5.0
        PRICE_ANOMALY_THRESHOLD = 0.03
        NEWS_CACHE_MINUTES = 60

        # Concentrazione settoriale
        SECTOR_MAP = {
                "AAPL": "Tech",
                    "MSFT": "Tech",
                        "GOOGL": "Tech",
                            "ENI.MI": "Energy",
                                "ISP.MI": "Banks",
                                    "UCG.MI": "Banks",
        }
        MAX_POSITIONS_PER_SECTOR = 2
        SECTOR_EXPOSURE_LOOKBACK_DAYS = 10

        # PDT Protection
        PDT_PROTECTION_ENABLED = True
        PDT_MAX_DAY_TRADES_5_DAYS = 3
        PDT_ACCOUNT_THRESHOLD_USD = 25000