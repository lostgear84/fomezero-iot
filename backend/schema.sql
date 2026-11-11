PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS leitura (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    lote_id        TEXT    NOT NULL,
    device_id      TEXT    NOT NULL,
    seq            INTEGER NOT NULL,
    ts             TEXT    NOT NULL,
    temp_c         REAL,
    umid_pct       REAL,
    caixa_presente INTEGER,
    distancia_cm   REAL,
    limite_c       REAL,
    evento         TEXT,
    estado         TEXT,
    origem         TEXT,
    payload_raw    TEXT,
    recebido_em    TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE (device_id, seq, ts)
);
CREATE INDEX IF NOT EXISTS ix_leitura_lote_ts ON leitura (lote_id, ts);

CREATE TABLE IF NOT EXISTS alerta (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    lote_id         TEXT NOT NULL,
    device_id       TEXT NOT NULL,
    seq             INTEGER,
    ts              TEXT NOT NULL,
    evento          TEXT NOT NULL,
    temp_c          REAL,
    limite_c        REAL DEFAULT 5.0,
    duracao_acima_s INTEGER,
    severidade      TEXT,
    estado          TEXT DEFAULT 'ativo',
    recebido_em     TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS ix_alerta_lote ON alerta (lote_id, ts);

CREATE VIEW IF NOT EXISTS vw_lotes_com_alerta AS
SELECT lote_id,
       COUNT(*)    AS qtd_alertas,
       MAX(temp_c) AS temp_max_c,
       MIN(ts)     AS primeiro_alerta,
       MAX(ts)     AS ultimo_alerta
FROM alerta
GROUP BY lote_id;

CREATE VIEW IF NOT EXISTS vw_resumo_lote AS
SELECT lote_id,
       COUNT(*)                                                      AS qtd_leituras,
       ROUND(AVG(temp_c), 2)                                         AS temp_media_c,
       ROUND(MAX(temp_c), 2)                                         AS temp_max_c,
       SUM(CASE WHEN evento = 'quebra_cadeia_frio' THEN 1 ELSE 0 END) AS leituras_em_alerta,
       MIN(ts) AS inicio, MAX(ts) AS fim
FROM leitura
GROUP BY lote_id;
