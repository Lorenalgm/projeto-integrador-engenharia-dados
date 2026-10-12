"""Caminhos, conexão com o banco e parâmetros usados por todas as etapas do pipeline."""
import os
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
RAW = RAIZ / 'data' / 'raw'
SQL = RAIZ / 'sql'
MODELOS = RAIZ / 'models'
RESULTADOS = RAIZ / 'reports'
LOGS = RAIZ / 'logs'

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql+psycopg2://localhost/projeto_integrador')

# fontes
COMPRAS_CSV = RAW / 'compras.csv'
CLIENTES_XLSX = RAW / 'clientes.xlsx'
PRODUTOS_JSON = RAW / 'produtos.json'
IBGE_URL = 'https://servicodados.ibge.gov.br/api/v1/localidades/municipios?view=nivelado'
IBGE_CACHE = RAW / 'ibge_municipios.json'
KAGGLE_DATASET = 'crisparada/brazilian-cities'
KAGGLE_ARQUIVO = 'BRAZIL_CITIES.csv'
KAGGLE_CSV = RAW / 'kaggle' / KAGGLE_ARQUIVO

# regras de negócio
HOJE = pd.Timestamp('2026-06-30')     # data de extração dos dados
CORTE = pd.Timestamp('2026-03-31')    # features usam compras até aqui; o target olha os 90 dias seguintes
JANELA_CHURN = 90
JANELA_ATIVO = 180
SEED = 42

SEGMENTOS = ['Bronze', 'Prata', 'Ouro']
CANAIS = ['Loja Física', 'Site', 'App']
PAGAMENTOS = ['Pix', 'Cartão de Crédito', 'Cartão de Débito', 'Boleto']
REGIOES = ['Norte', 'Nordeste', 'Centro-Oeste', 'Sudeste', 'Sul']
