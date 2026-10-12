"""Features: transforma as compras do PostgreSQL em uma linha por cliente, com as features e o target `churn`.

O churn é definido com uma data de corte: as features usam só as compras até o corte e o target olha os
90 dias seguintes. Assim nenhuma informação do futuro entra nas features (sem vazamento).
"""
import logging

import numpy as np
import pandas as pd

from src import config, load

log = logging.getLogger('pipeline')

ORDEM_SEGMENTO = {'Bronze': 0, 'Prata': 1, 'Ouro': 2}
CANAIS_ONLINE = ['Site', 'App']

# (feature, grupo, fonte, como é calculada, o que representa e por que ajuda)
DOCUMENTACAO = [
    ('idade', 'Cadastro', 'Excel', 'Anos entre data_nascimento e a data de corte',
     'Clientes mais jovens trocam de loja com mais facilidade. Fica nula quando o nascimento é inválido'),
    ('segmento_cod', 'Cadastro', 'Excel', 'Bronze = 0, Prata = 1, Ouro = 2 (encoding ordinal)',
     'Nível no programa de fidelidade. Tem ordem, por isso vira um número só'),
    ('dias_desde_cadastro', 'Temporal', 'Excel', 'Dias entre data_cadastro e a data de corte',
     'Tempo de relacionamento com a loja'),
    ('dias_sem_comprar', 'Temporal', 'CSV', 'Dias entre a última compra e a data de corte',
     'Recência: quanto mais tempo parado, maior a chance de já ter abandonado'),
    ('intervalo_medio_dias', 'Temporal', 'CSV', 'Dias entre a primeira e a última compra, dividido por (compras - 1)',
     'Ritmo normal do cliente. Com uma compra só, usa os dias desde essa compra'),
    ('atraso_relativo', 'Temporal', 'CSV', 'dias_sem_comprar / intervalo_medio_dias',
     'Compara a pausa atual com o ritmo do próprio cliente: 60 dias parado é normal para uns e alarme para outros'),
    ('pct_compras_fim_de_semana', 'Temporal', 'CSV + dim_data', 'Parcela das compras feitas em sábado ou domingo',
     'Hábito de compra (lazer no fim de semana ou rotina durante a semana)'),
    ('qtd_compras', 'Agregação', 'CSV', 'Número de compras até o corte', 'Frequência: volume de relacionamento'),
    ('total_gasto', 'Agregação', 'CSV', 'Soma do valor das compras até o corte', 'Valor monetário do cliente'),
    ('ticket_medio', 'Agregação', 'CSV', 'total_gasto / qtd_compras', 'Tamanho típico de cada compra'),
    ('categorias_distintas', 'Agregação', 'CSV + JSON', 'Número de categorias diferentes compradas',
     'Quem compra de vários esportes depende mais da loja'),
    ('margem_pct', 'Agregação', 'CSV + JSON', '(valor - custo) / valor, somando todas as compras',
     'Usa o custo do catálogo. Margem baixa indica cliente que só compra em promoção'),
    ('pct_compras_online', 'Agregação', 'CSV', 'Parcela das compras feitas pelo Site ou pelo App',
     'Compra online depende de entrega, que pesa mais longe do centro de distribuição'),
    ('qtd_compras_90d', 'Agregação', 'CSV', 'Compras nos 90 dias antes do corte', 'Atividade recente'),
    ('gasto_90d', 'Agregação', 'CSV', 'Valor gasto nos 90 dias antes do corte', 'Atividade recente em reais'),
    ('tendencia_compras', 'Agregação', 'CSV', 'qtd_compras_90d menos as compras dos 90 dias anteriores',
     'Negativa quando o cliente está desacelerando'),
    ('compras_por_mes', 'Agregação', 'CSV', 'qtd_compras / meses desde a primeira compra', 'Frequência ajustada ao tempo de casa'),
    ('canal_*', 'Encoding', 'CSV', 'One-hot do canal mais usado pelo cliente (Loja Física, Site, App)',
     'Canal preferido, sem ordem entre as opções'),
    ('regiao_*', 'Encoding', 'API IBGE', 'One-hot da região do município do cliente (5 colunas)',
     'Distância do centro de distribuição. Cliente sem cidade fica com zero nas cinco'),
    ('capital', 'Localidade', 'Kaggle', '1 se o município é capital de estado', 'Capitais têm mais concorrência e mais oferta de lojas'),
    ('populacao_log', 'Localidade', 'Kaggle', 'log10 da população estimada do município', 'Porte da cidade, em escala logarítmica por causa de São Paulo'),
    ('idhm', 'Localidade', 'Kaggle', 'Índice de Desenvolvimento Humano Municipal', 'Indicador social da cidade do cliente'),
    ('pib_per_capita', 'Localidade', 'Kaggle', 'PIB per capita do município, em reais', 'Poder de compra médio da cidade'),
]


def ler_compras(engine):
    """Lê do PostgreSQL a visão que junta o fato com as dimensões."""
    df = load.ler(engine, 'SELECT * FROM dw.vw_compras ORDER BY id_compra')
    for col in ['data_compra', 'data_nascimento', 'data_cadastro']:
        df[col] = pd.to_datetime(df[col])
    return df


def criar_features(compras, corte=config.CORTE):
    """Uma linha por cliente ativo no corte (comprou nos últimos 180 dias), com as features e o target."""
    hist = compras[compras['data_compra'] <= corte].copy()
    futuro = compras[(compras['data_compra'] > corte)
                     & (compras['data_compra'] <= corte + pd.Timedelta(days=config.JANELA_CHURN))]

    ultima = hist.groupby('cliente_id')['data_compra'].max()
    ativos = ultima[(corte - ultima).dt.days < config.JANELA_ATIVO].index
    hist = hist[hist['cliente_id'].isin(ativos)].sort_values(['cliente_id', 'data_compra'])
    hist['dias_ate_corte'] = (corte - hist['data_compra']).dt.days
    hist['online'] = hist['canal'].isin(CANAIS_ONLINE)
    g = hist.groupby('cliente_id')

    # cadastro e localidade (iguais em todas as compras do cliente)
    t = g.agg(segmento=('segmento', 'first'), regiao=('regiao', 'first'), capital=('capital', 'first'),
              populacao=('populacao', 'first'), idhm=('idhm', 'first'), pib_per_capita=('pib_per_capita', 'first'),
              canal_preferido=('canal', lambda s: s.mode().iloc[0]))
    t['idade'] = ((corte - g['data_nascimento'].first()).dt.days / 365.25).round(1)
    t['dias_desde_cadastro'] = (corte - g['data_cadastro'].first()).dt.days

    # temporais
    t['dias_sem_comprar'] = g['dias_ate_corte'].min()
    primeira, n_compras = g['dias_ate_corte'].max(), g.size()
    intervalo = (primeira - t['dias_sem_comprar']) / (n_compras - 1).where(n_compras > 1)
    t['intervalo_medio_dias'] = intervalo.fillna(primeira).clip(lower=1)
    t['atraso_relativo'] = t['dias_sem_comprar'] / t['intervalo_medio_dias']
    t['pct_compras_fim_de_semana'] = g['fim_de_semana'].mean()

    # agregações
    t = t.join(g.agg(qtd_compras=('valor', 'count'), total_gasto=('valor', 'sum'), ticket_medio=('valor', 'mean'),
                     categorias_distintas=('categoria', 'nunique')))
    t['margem_pct'] = g['margem'].sum() / t['total_gasto']
    t['pct_compras_online'] = g['online'].mean()
    ult90 = hist[hist['dias_ate_corte'] < 90].groupby('cliente_id')
    ant90 = hist[hist['dias_ate_corte'].between(90, 179)].groupby('cliente_id')
    t['qtd_compras_90d'] = ult90.size().reindex(t.index, fill_value=0)
    t['gasto_90d'] = ult90['valor'].sum().reindex(t.index, fill_value=0.0)
    t['tendencia_compras'] = t['qtd_compras_90d'] - ant90.size().reindex(t.index, fill_value=0)
    t['compras_por_mes'] = t['qtd_compras'] / ((primeira + 1) / 30).clip(lower=1)

    t['churn'] = (~t.index.isin(futuro['cliente_id'])).astype(int)
    return t


def codificar(clientes):
    """Aplica os encodings e devolve só colunas numéricas. Nulos continuam nulos: o Pipeline do modelo imputa."""
    X = clientes.drop(columns='churn', errors='ignore').copy()
    X['segmento_cod'] = X.pop('segmento').map(ORDEM_SEGMENTO)
    for canal in config.CANAIS:
        X[f'canal_{canal}'] = (X['canal_preferido'] == canal).astype(int)
    for regiao in config.REGIOES:
        X[f'regiao_{regiao}'] = (X['regiao'] == regiao).astype(int)
    X['capital'] = X['capital'].astype(float)
    X['populacao_log'] = np.log10(X.pop('populacao').astype(float))
    return X.drop(columns=['canal_preferido', 'regiao']).astype(float)


def colunas_de_localidade(X):
    """Features que só existem por causa das fontes externas (API do IBGE e Kaggle)."""
    return [c for c in X.columns if c.startswith('regiao_') or c in ('capital', 'populacao_log', 'idhm', 'pib_per_capita')]


def preparar(engine):
    """PostgreSQL -> (X, y, tabela por cliente). Também grava a tabela em ml.features_cliente."""
    clientes = criar_features(ler_compras(engine))
    X, y = codificar(clientes), clientes['churn']
    X.join(y).reset_index().to_sql('features_cliente', engine, schema='ml', if_exists='replace', index=False)
    log.info('features  | %d clientes ativos | %d features | churn %.1f%% | gravado em ml.features_cliente',
             len(X), X.shape[1], 100 * y.mean())
    return X, y, clientes


def documentacao():
    return pd.DataFrame(DOCUMENTACAO, columns=['feature', 'grupo', 'fonte', 'como é calculada', 'o que representa e por que ajuda'])
