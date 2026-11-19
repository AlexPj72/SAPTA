-- Rollback della migrazione 20261119_fx_rates.sql
-- ATTENZIONE: prima di eseguirlo riportare E e T al commit precedente l'integrazione fx_rates (git revert),
-- altrimenti E e T si fermano con errore esplicito perche' la tabella non esiste (nessun ripiego su altre fonti).
-- Elimina SOLO la tabella fx_rates (creata dalla migrazione): nessun altro dato viene toccato.

drop table if exists public.fx_rates;
