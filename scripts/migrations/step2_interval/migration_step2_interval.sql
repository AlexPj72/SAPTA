-- SAPTA v5.1 — STEP 2
-- Migrazione: rendere esplicito l'intervallo (15m / 1d) nella tabella `prezzi`.
--
-- IMPORTANTE: eseguire prima check_prezzi_schema.py e confermare che i nomi
-- di colonna qui sotto (ticker, timestamp) corrispondano allo schema reale.
-- Se i nomi differiscono, aggiornare questo script di conseguenza PRIMA di
-- eseguirlo — non eseguire alla cieca su produzione.
--
-- Lo script è scritto per essere IDEMPOTENTE: può essere eseguito più volte
-- senza effetti collaterali se applicato parzialmente in precedenza.

-- 1) Aggiunge la colonna 'interval' se non esiste già.
--    Assunzione esplicita: i dati storici presenti in `prezzi` prima di
--    questa migrazione sono tutti intraday (coerente con la Sezione 4.1
--    della spec, che descrive `prezzi` come tabella nata per l'intraday).
--    Se questa assunzione è sbagliata per il tuo dataset, NON eseguire il
--    backfill automatico sotto (punto 2) e valorizzalo manualmente.
ALTER TABLE prezzi
    ADD COLUMN IF NOT EXISTS interval TEXT;

-- 2) Backfill dei record esistenti che hanno interval NULL.
--    Eseguito solo sui record NULL, quindi sicuro da rilanciare più volte.
--    ATTENZIONE: verifica l'assunzione del punto 1 prima di eseguire questa
--    riga. Se il dataset contiene già uno storico giornaliero mescolato,
--    commenta questa riga e fai il backfill manualmente per range di date.
UPDATE prezzi
SET interval = '15m'
WHERE interval IS NULL;

-- 3) Vincolo di dominio: solo i due valori previsti dalla spec.
--    Il blocco DO evita errori se il constraint esiste già.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'prezzi_interval_check'
    ) THEN
        ALTER TABLE prezzi
            ADD CONSTRAINT prezzi_interval_check
            CHECK (interval IN ('15m', '1d'));
    END IF;
END $$;

-- 4) Ora che è popolata e vincolata, rendila NOT NULL.
--    Fallisce in modo esplicito se sono rimasti NULL: meglio fermarsi qui
--    che avere righe ambigue in produzione.
ALTER TABLE prezzi
    ALTER COLUMN interval SET NOT NULL;

-- 5) Indice richiesto dalla Sezione 4.1 della spec:
--    (ticker, interval, timestamp DESC)
--    Nome esplicito per poterlo verificare/droppare in futuro senza ambiguità.
CREATE INDEX IF NOT EXISTS idx_prezzi_ticker_interval_timestamp
    ON prezzi (ticker, interval, timestamp DESC);

-- 6) Verifica finale: conta quante righe per intervallo, da controllare
--    manualmente dopo l'esecuzione (non blocca la migrazione).
SELECT interval, COUNT(*) AS n_righe
FROM prezzi
GROUP BY interval;
