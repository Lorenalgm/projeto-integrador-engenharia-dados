-- Estrutura do banco projeto_integrador. Executado pelo pipeline (src/load.py) a cada carga completa.
--
--   staging  cópia fiel de cada fonte, tudo como texto (criado pelo pandas na carga)
--   dw       modelo estrela com os dados limpos e integrados
--   ml       features por cliente, métricas e previsões do modelo

DROP SCHEMA IF EXISTS staging CASCADE;
DROP SCHEMA IF EXISTS dw CASCADE;
DROP SCHEMA IF EXISTS ml CASCADE;
CREATE SCHEMA staging;
CREATE SCHEMA dw;
CREATE SCHEMA ml;

-- ========== dimensões ==========

-- Municípios do IBGE (API) enriquecidos com os indicadores do Kaggle
CREATE TABLE dw.dim_localidade (
    codigo_ibge     INTEGER PRIMARY KEY,
    municipio       TEXT NOT NULL,
    uf              CHAR(2) NOT NULL,
    estado          TEXT NOT NULL,
    regiao          TEXT NOT NULL CHECK (regiao IN ('Norte', 'Nordeste', 'Centro-Oeste', 'Sudeste', 'Sul')),
    capital         BOOLEAN,
    populacao       INTEGER CHECK (populacao > 0),
    idhm            NUMERIC(4, 3) CHECK (idhm BETWEEN 0 AND 1),
    pib_per_capita  NUMERIC(12, 2) CHECK (pib_per_capita > 0),
    UNIQUE (municipio, uf)
);

CREATE TABLE dw.dim_cliente (
    cliente_id       INTEGER PRIMARY KEY,
    nome             TEXT NOT NULL,
    email            TEXT,
    data_nascimento  DATE,
    segmento         TEXT NOT NULL CHECK (segmento IN ('Bronze', 'Prata', 'Ouro')),
    data_cadastro    DATE NOT NULL,
    codigo_ibge      INTEGER REFERENCES dw.dim_localidade (codigo_ibge)
);

CREATE TABLE dw.dim_produto (
    produto_id  TEXT PRIMARY KEY,
    nome        TEXT NOT NULL,
    categoria   TEXT NOT NULL,
    preco       NUMERIC(10, 2) NOT NULL CHECK (preco > 0),
    custo       NUMERIC(10, 2) NOT NULL CHECK (custo > 0)
);

CREATE TABLE dw.dim_data (
    data           DATE PRIMARY KEY,
    ano            SMALLINT NOT NULL,
    trimestre      SMALLINT NOT NULL CHECK (trimestre BETWEEN 1 AND 4),
    mes            SMALLINT NOT NULL CHECK (mes BETWEEN 1 AND 12),
    nome_mes       TEXT NOT NULL,
    dia_semana     SMALLINT NOT NULL CHECK (dia_semana BETWEEN 0 AND 6),   -- 0 = segunda
    nome_dia       TEXT NOT NULL,
    fim_de_semana  BOOLEAN NOT NULL
);

-- ========== fato ==========

CREATE TABLE dw.fato_compras (
    id_compra    INTEGER PRIMARY KEY,
    cliente_id   INTEGER NOT NULL REFERENCES dw.dim_cliente (cliente_id),
    produto_id   TEXT NOT NULL REFERENCES dw.dim_produto (produto_id),
    data_compra  DATE NOT NULL REFERENCES dw.dim_data (data),
    quantidade   SMALLINT NOT NULL CHECK (quantidade BETWEEN 1 AND 20),
    valor        NUMERIC(12, 2) NOT NULL CHECK (valor > 0),
    custo_total  NUMERIC(12, 2) NOT NULL CHECK (custo_total > 0),
    canal        TEXT NOT NULL CHECK (canal IN ('Loja Física', 'Site', 'App')),
    pagamento    TEXT NOT NULL
);
CREATE INDEX idx_fato_cliente ON dw.fato_compras (cliente_id);
CREATE INDEX idx_fato_data ON dw.fato_compras (data_compra);
CREATE INDEX idx_fato_produto ON dw.fato_compras (produto_id);

-- ========== controle do ETL ==========

-- Quantas linhas entraram, foram removidas e restaram em cada etapa de cada fonte
CREATE TABLE dw.etl_etapas (
    ordem       SERIAL PRIMARY KEY,
    fonte       TEXT NOT NULL,
    etapa       TEXT NOT NULL,
    entraram    INTEGER NOT NULL,
    removidos   INTEGER NOT NULL,
    restaram    INTEGER NOT NULL,
    descricao   TEXT NOT NULL,
    executado_em TIMESTAMP NOT NULL DEFAULT now()
);

-- ========== visão para análise e para as features ==========

CREATE VIEW dw.vw_compras AS
SELECT f.id_compra, f.data_compra, d.ano, d.mes, d.dia_semana, d.fim_de_semana,
       f.cliente_id, c.segmento, c.data_nascimento, c.data_cadastro,
       l.municipio, l.uf, l.regiao, l.capital, l.populacao, l.idhm, l.pib_per_capita,
       f.produto_id, p.nome AS produto, p.categoria,
       f.quantidade, f.valor, f.custo_total, f.valor - f.custo_total AS margem,
       f.canal, f.pagamento
FROM dw.fato_compras f
JOIN dw.dim_cliente c USING (cliente_id)
JOIN dw.dim_produto p USING (produto_id)
JOIN dw.dim_data d ON d.data = f.data_compra
LEFT JOIN dw.dim_localidade l USING (codigo_ibge);

-- ========== resultados do modelo ==========

CREATE TABLE ml.metricas_modelo (
    modelo         TEXT PRIMARY KEY,
    escolhido      BOOLEAN NOT NULL,
    cv_f1          NUMERIC(6, 4) NOT NULL,
    cv_f1_desvio   NUMERIC(6, 4) NOT NULL,
    cv_roc_auc     NUMERIC(6, 4) NOT NULL,
    accuracy       NUMERIC(6, 4) NOT NULL,
    precision      NUMERIC(6, 4) NOT NULL,
    recall         NUMERIC(6, 4) NOT NULL,
    f1             NUMERIC(6, 4) NOT NULL,
    roc_auc        NUMERIC(6, 4) NOT NULL,
    treinado_em    TIMESTAMP NOT NULL DEFAULT now()
);
