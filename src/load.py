"""Load: cria o banco e a estrutura, grava o dado bruto em staging e o dado limpo no modelo estrela."""
import logging

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from src import config

log = logging.getLogger('pipeline')

# ordem de carga: as dimensões entram antes de quem aponta para elas
ORDEM_DW = ['dim_localidade', 'dim_cliente', 'dim_produto', 'dim_data', 'fato_compras']


def conectar(url=config.DATABASE_URL):
    """Devolve a engine do banco do projeto, criando o banco se ele ainda não existir."""
    destino = make_url(url)
    admin = create_engine(destino.set(database='postgres'), isolation_level='AUTOCOMMIT')
    with admin.connect() as con:
        existe = con.execute(text('SELECT 1 FROM pg_database WHERE datname = :nome'), {'nome': destino.database}).scalar()
        if not existe:
            con.execute(text(f'CREATE DATABASE "{destino.database}"'))
            log.info('load      | banco %s criado', destino.database)
    admin.dispose()
    return create_engine(url)


def criar_estrutura(engine):
    """Executa sql/schema.sql: recria os schemas staging, dw e ml (carga completa)."""
    with engine.begin() as con:
        con.exec_driver_sql((config.SQL / 'schema.sql').read_text())
    log.info('load      | estrutura recriada a partir de sql/schema.sql')


def carregar_staging(engine, fontes):
    """Grava cada fonte como chegou, em texto, para dar rastreabilidade ao que foi rejeitado na limpeza."""
    for nome, df in fontes.items():
        bruto = df.rename(columns=lambda c: c.strip().lower().replace('-', '_'))
        bruto.to_sql(nome, engine, schema='staging', if_exists='replace', index=False, chunksize=5000, method='multi')
        log.info('load      | staging.%-16s | %6d linhas', nome, len(bruto))


def carregar_dw(engine, tabelas, etapas):
    """Insere dimensões e fato nas tabelas criadas pelo schema.sql, em uma única transação."""
    with engine.begin() as con:
        for nome in ORDEM_DW:
            tabelas[nome].to_sql(nome, con, schema='dw', if_exists='append', index=False, chunksize=5000, method='multi')
            log.info('load      | dw.%-21s | %6d linhas', nome, len(tabelas[nome]))
        etapas.to_sql('etl_etapas', con, schema='dw', if_exists='append', index=False)


def verificar(engine, tabelas):
    """Confere no PostgreSQL se o que foi gravado bate com o que saiu da transformação."""
    with engine.connect() as con:
        for nome in ORDEM_DW:
            gravadas = con.execute(text(f'SELECT count(*) FROM dw.{nome}')).scalar()
            assert gravadas == len(tabelas[nome]), f'dw.{nome}: {gravadas} linhas no banco, {len(tabelas[nome])} esperadas'
        receita = float(con.execute(text('SELECT sum(valor) FROM dw.fato_compras')).scalar())
        esperado = float(tabelas['fato_compras']['valor'].sum())
        assert abs(receita - esperado) < 0.01, f'receita no banco ({receita}) diferente da transformada ({esperado})'
        na_visao = con.execute(text('SELECT count(*) FROM dw.vw_compras')).scalar()
        assert na_visao == len(tabelas['fato_compras']), 'a visão vw_compras perdeu linhas nas junções'
    log.info('verify    | contagens, receita (R$ %.2f) e junções conferidas no PostgreSQL', receita)


def ler(engine, sql):
    """Consulta o banco e devolve um DataFrame."""
    with engine.connect() as con:
        return pd.read_sql(text(sql), con)
