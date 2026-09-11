# src/universe.py
# SAPTA v5.1 — Universo investibile curato

LIQ_HIGH = "LIQ_HIGH"
LIQ_MEDIUM = "LIQ_MEDIUM"
LIQ_LOW = "LIQ_LOW"

# USA: titoli ad alta liquidità
UNIVERSE_USA = {
    "AAPL": LIQ_HIGH, "MSFT": LIQ_HIGH, "NVDA": LIQ_HIGH, "AMZN": LIQ_HIGH,
    "GOOGL": LIQ_HIGH, "GOOG": LIQ_HIGH, "META": LIQ_HIGH, "AVGO": LIQ_HIGH,
    "TSLA": LIQ_HIGH, "BRK-B": LIQ_HIGH, "JPM": LIQ_HIGH, "V": LIQ_HIGH,
    "MA": LIQ_HIGH, "WMT": LIQ_HIGH, "LLY": LIQ_HIGH, "JNJ": LIQ_HIGH,
    "XOM": LIQ_HIGH, "PG": LIQ_HIGH, "HD": LIQ_HIGH, "COST": LIQ_HIGH,
    "ORCL": LIQ_HIGH, "NFLX": LIQ_HIGH, "CRM": LIQ_HIGH, "AMD": LIQ_HIGH,
    "INTC": LIQ_HIGH, "QCOM": LIQ_HIGH, "MU": LIQ_HIGH, "TXN": LIQ_HIGH,
    "AMAT": LIQ_HIGH, "ADI": LIQ_HIGH, "CSCO": LIQ_HIGH, "IBM": LIQ_HIGH,
    "UBER": LIQ_HIGH, "ABNB": LIQ_HIGH, "PYPL": LIQ_HIGH, "ADBE": LIQ_HIGH,
    "NOW": LIQ_HIGH, "PANW": LIQ_HIGH, "INTU": LIQ_HIGH, "ISRG": LIQ_HIGH,
    "CAT": LIQ_HIGH, "GE": LIQ_HIGH, "RTX": LIQ_HIGH, "BA": LIQ_HIGH,
    "HON": LIQ_HIGH, "UNP": LIQ_HIGH, "DE": LIQ_HIGH, "LOW": LIQ_HIGH,
    "NKE": LIQ_HIGH, "MCD": LIQ_HIGH, "SBUX": LIQ_HIGH, "KO": LIQ_HIGH,
    "PEP": LIQ_HIGH, "PM": LIQ_HIGH, "MO": LIQ_HIGH, "CVX": LIQ_HIGH,
    "COP": LIQ_HIGH, "SLB": LIQ_HIGH, "EOG": LIQ_HIGH, "PFE": LIQ_HIGH,
    "MRK": LIQ_HIGH, "ABBV": LIQ_HIGH, "BMY": LIQ_HIGH, "AMGN": LIQ_HIGH,
    "GILD": LIQ_HIGH, "TMO": LIQ_HIGH, "DHR": LIQ_HIGH, "ABT": LIQ_HIGH,
    "MDT": LIQ_HIGH, "LMT": LIQ_HIGH, "PLTR": LIQ_HIGH, "CRWD": LIQ_HIGH,
    "SNOW": LIQ_HIGH, "SHOP": LIQ_HIGH, "COIN": LIQ_HIGH, "MELI": LIQ_HIGH,
    "BKNG": LIQ_HIGH, "MAR": LIQ_HIGH, "DIS": LIQ_HIGH, "CMCSA": LIQ_HIGH,
    "T": LIQ_HIGH, "VZ": LIQ_HIGH, "NEE": LIQ_HIGH, "DUK": LIQ_HIGH,
    "SO": LIQ_HIGH, "UPS": LIQ_HIGH, "FDX": LIQ_HIGH, "GS": LIQ_HIGH,
    "MS": LIQ_HIGH, "BAC": LIQ_HIGH, "C": LIQ_HIGH, "WFC": LIQ_HIGH,
    "AXP": LIQ_HIGH, "BLK": LIQ_HIGH, "SPGI": LIQ_HIGH, "MCO": LIQ_HIGH,
    "ICE": LIQ_HIGH, "CME": LIQ_HIGH,
}

# Italia: FTSE MIB + large/mid cap inizialmente trattabili
UNIVERSE_IT = {
    "ENI.MI": LIQ_HIGH, "ISP.MI": LIQ_HIGH, "UCG.MI": LIQ_HIGH,
    "ENEL.MI": LIQ_HIGH, "STLAM.MI": LIQ_HIGH, "STMMI.MI": LIQ_HIGH,
    "TIT.MI": LIQ_HIGH, "RACE.MI": LIQ_HIGH, "MONC.MI": LIQ_HIGH,
    "G.MI": LIQ_HIGH, "LDO.MI": LIQ_HIGH, "BAMI.MI": LIQ_HIGH,
    "MB.MI": LIQ_HIGH, "BC.MI": LIQ_HIGH, "BMED.MI": LIQ_HIGH,
    "BMPS.MI": LIQ_HIGH, "BPE.MI": LIQ_HIGH, "A2A.MI": LIQ_HIGH,
    "HER.MI": LIQ_HIGH, "REC.MI": LIQ_HIGH, "TRN.MI": LIQ_HIGH,
    "PST.MI": LIQ_HIGH,
    "SRG.MI": LIQ_MEDIUM, "PRY.MI": LIQ_MEDIUM, "IP.MI": LIQ_MEDIUM,
    "IG.MI": LIQ_MEDIUM, "CPR.MI": LIQ_MEDIUM, "AMP.MI": LIQ_MEDIUM,
    "BPSO.MI": LIQ_MEDIUM, "ERG.MI": LIQ_MEDIUM, "IVG.MI": LIQ_MEDIUM,
    "IRE.MI": LIQ_MEDIUM, "DIA.MI": LIQ_MEDIUM, "INW.MI": LIQ_MEDIUM,
    "SOL.MI": LIQ_MEDIUM, "JUVE.MI": LIQ_MEDIUM,
    "AVIO.MI": LIQ_LOW,
    # "TECH.MI" rimosso: nessun riscontro come ticker Yahoo/yfinance valido.
    # Se intendevi Technogym o Technoprobe, i simboli corretti sono
    # "TGYM.MI" e "TPRO.MI" rispettivamente — verificare e reinserire.
}

UNIVERSE_FULL = list(dict.fromkeys(
    list(UNIVERSE_USA) + list(UNIVERSE_IT)
))

def get_universe():
    return UNIVERSE_FULL.copy()

def get_liquidity_bucket(ticker):
    if ticker in UNIVERSE_USA:
        return UNIVERSE_USA[ticker]
    if ticker in UNIVERSE_IT:
        return UNIVERSE_IT[ticker]
    raise KeyError(f"Ticker non presente nell'universo SAPTA: {ticker}")

def get_universe_metadata():
    return {
        ticker: {
            "market": "USA" if ticker in UNIVERSE_USA else "IT",
            "liquidity_bucket": get_liquidity_bucket(ticker),
        }
        for ticker in UNIVERSE_FULL
    }

assert len(UNIVERSE_FULL) == len(set(UNIVERSE_FULL))
