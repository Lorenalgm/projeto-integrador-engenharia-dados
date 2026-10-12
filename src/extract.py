"""Extract: lê as cinco fontes e devolve cada uma como DataFrame de texto, sem nenhum tratamento.

    1. CSV     data/raw/compras.csv         compras do sistema de vendas
    2. Excel   data/raw/clientes.xlsx       cadastro de clientes do CRM
    3. JSON    data/raw/produtos.json       catálogo aninhado por categoria
    4. API     IBGE Localidades             município, UF e região (dado real)
    5. Kaggle  crisparada/brazilian-cities  população, IDHM e PIB per capita por município (dado real)
"""
import json
import logging
import shutil
import tempfile
import time
from pathlib import Path

import pandas as pd
import requests

from src import config

log = logging.getLogger('pipeline')

COLUNAS_KAGGLE = ['CITY', 'STATE', 'CAPITAL', 'IBGE_RES_POP', 'ESTIMATED_POP', 'IDHM', 'GDP_CAPITA']


def ler_compras(caminho=config.COMPRAS_CSV):
    return pd.read_csv(caminho, dtype=str)


def ler_clientes(caminho=config.CLIENTES_XLSX):
    return pd.read_excel(caminho, dtype=str)


def ler_produtos(caminho=config.PRODUTOS_JSON):
    """Achata o JSON (categorias -> produtos) em uma linha por produto."""
    catalogo = json.loads(Path(caminho).read_text())
    return pd.json_normalize(catalogo['categorias'], record_path='produtos', meta='categoria').astype(str)


def ler_municipios_ibge(url=config.IBGE_URL, cache=config.IBGE_CACHE, tentativas=3):
    """Consulta a API do IBGE e guarda a resposta em disco. Se a API não responder, usa a última resposta guardada."""
    for tentativa in range(1, tentativas + 1):
        try:
            resposta = requests.get(url, timeout=30)
            resposta.raise_for_status()
            municipios = resposta.json()
            cache.write_text(json.dumps(municipios, ensure_ascii=False))
            log.info('IBGE: %d municípios recebidos da API', len(municipios))
            break
        except (requests.RequestException, ValueError) as erro:
            log.warning('IBGE: tentativa %d de %d falhou (%s)', tentativa, tentativas, erro)
            time.sleep(2 * tentativa)
    else:
        if not cache.exists():
            raise RuntimeError('API do IBGE fora do ar e sem resposta guardada em disco')
        municipios = json.loads(cache.read_text())
        log.warning('IBGE: usando a resposta guardada em %s (%d municípios)', cache.name, len(municipios))
    return pd.DataFrame(municipios).astype('string').astype(object)


def baixar_kaggle(destino=config.KAGGLE_CSV):
    """Baixa o dataset pela API do Kaggle (precisa de ~/.kaggle/kaggle.json ou KAGGLE_USERNAME e KAGGLE_KEY)."""
    from kaggle.api.kaggle_api_extended import KaggleApi   # importa aqui porque só autentica quando precisa baixar

    api = KaggleApi()
    api.authenticate()
    with tempfile.TemporaryDirectory() as pasta:
        api.dataset_download_files(config.KAGGLE_DATASET, path=pasta, unzip=True, quiet=True)
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(Path(pasta) / config.KAGGLE_ARQUIVO, destino)
    log.info('Kaggle: %s baixado de %s', destino.name, config.KAGGLE_DATASET)


def ler_cidades_kaggle(caminho=config.KAGGLE_CSV):
    """Lê o CSV do Kaggle. O arquivo fica versionado no repositório; se não existir, é baixado pela API."""
    if not caminho.exists():
        baixar_kaggle(caminho)
    return pd.read_csv(caminho, sep=';', dtype=str, usecols=COLUNAS_KAGGLE)


def extrair():
    """Lê todas as fontes. Devolve {nome da fonte: DataFrame bruto}."""
    fontes = {
        'compras': ler_compras(),
        'clientes': ler_clientes(),
        'produtos': ler_produtos(),
        'municipios_ibge': ler_municipios_ibge(),
        'cidades_kaggle': ler_cidades_kaggle(),
    }
    for nome, df in fontes.items():
        log.info('extract   | %-16s | %6d linhas | %2d colunas', nome, len(df), df.shape[1])
    return fontes
