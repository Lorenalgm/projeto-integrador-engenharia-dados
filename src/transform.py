"""Transform: limpa cada fonte e integra tudo nas tabelas do modelo estrela.

Cada função recebe os DataFrames brutos (texto) e devolve a tabela pronta para o PostgreSQL. A classe
Etapas registra quantas linhas entraram, foram removidas e restaram em cada passo.
"""
import logging
import unicodedata

import pandas as pd

from src import config

log = logging.getLogger('pipeline')

MESES = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro',
         'Outubro', 'Novembro', 'Dezembro']
DIAS = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']
# preço unitário aceito em relação ao preço de tabela (promoções chegam a 15% de desconto)
PRECO_MIN, PRECO_MAX = 0.5, 1.1


class Etapas:
    """Contagem de linhas por etapa de limpeza de todas as fontes."""

    def __init__(self):
        self.linhas = []

    def registrar(self, fonte, etapa, entraram, restaram, descricao):
        self.linhas.append({'fonte': fonte, 'etapa': etapa, 'entraram': entraram,
                            'removidos': entraram - restaram, 'restaram': restaram, 'descricao': descricao})
        log.info('transform | %-11s | %-22s | entraram %6d | removidos %5d | restaram %6d',
                 fonte, etapa, entraram, entraram - restaram, restaram)

    def tabela(self):
        return pd.DataFrame(self.linhas)


# ========= funções de limpeza =========
def para_numero(serie):
    """Converte '1299.9' e 'R$ 1.299,90' para float; o que não for número vira NaN."""
    s = serie.astype('string').str.strip()
    com_virgula = s.str.contains(',', na=False)
    s = s.str.replace('R$', '', regex=False).str.strip()
    s = s.mask(com_virgula, s.str.replace('.', '', regex=False).str.replace(',', '.', regex=False))
    return pd.to_numeric(s, errors='coerce')


def para_data(serie):
    """Aceita AAAA-MM-DD e DD/MM/AAAA; data impossível ou texto solto vira NaT."""
    s = serie.astype('string').str.strip()
    iso = pd.to_datetime(s, format='%Y-%m-%d', errors='coerce')
    return iso.fillna(pd.to_datetime(s, format='%d/%m/%Y', errors='coerce'))


def chave(texto):
    """Minúsculas, sem acento e sem espaços nas pontas: serve para comparar grafias."""
    sem = unicodedata.normalize('NFKD', str(texto).strip().lower())
    return ''.join(c for c in sem if not unicodedata.combining(c))


def padronizar(serie, oficiais):
    """Troca cada grafia pela oficial ('  OURO ' -> 'Ouro'); o que não bate com nenhuma vira nulo."""
    mapa = {chave(o): o for o in oficiais}
    return serie.map(lambda v: mapa.get(chave(v)) if isinstance(v, str) else None)


def chave_municipio(nome, uf):
    return nome.map(chave, na_action='ignore') + '|' + uf.str.strip().str.upper()


# ========= dimensões =========
def montar_localidades(ibge, kaggle, etapas):
    """Municípios da API do IBGE, com população, IDHM e PIB per capita vindos do Kaggle (junção por nome + UF)."""
    loc = pd.DataFrame({
        'codigo_ibge': pd.to_numeric(ibge['municipio-id']),
        'municipio': ibge['municipio-nome'].str.strip(),
        'uf': ibge['UF-sigla'], 'estado': ibge['UF-nome'], 'regiao': ibge['regiao-nome'],
    })
    antes = len(loc)
    loc = loc.dropna(subset=['uf', 'regiao']).drop_duplicates('codigo_ibge')
    etapas.registrar('localidades', 'municípios do IBGE', antes, len(loc), 'Remove município sem UF ou região na resposta da API')

    ind = pd.DataFrame({
        'chave': chave_municipio(kaggle['CITY'], kaggle['STATE']),
        'capital': kaggle['CAPITAL'].str.strip() == '1',
        'populacao': para_numero(kaggle['ESTIMATED_POP']).fillna(para_numero(kaggle['IBGE_RES_POP'])),
        'idhm': para_numero(kaggle['IDHM']),
        'pib_per_capita': para_numero(kaggle['GDP_CAPITA']),
    }).drop_duplicates('chave')
    for col in ['populacao', 'idhm', 'pib_per_capita']:
        ind[col] = ind[col].where(ind[col] > 0)

    loc['chave'] = chave_municipio(loc['municipio'], loc['uf'])
    loc = loc.merge(ind, on='chave', how='left', validate='one_to_one').drop(columns='chave')
    com_indicador = int(loc['idhm'].notna().sum())
    etapas.registrar('localidades', 'indicadores do Kaggle', len(loc), len(loc),
                     f'Junção por nome + UF: {com_indicador} municípios com IDHM, {len(loc) - com_indicador} ficam sem indicador')
    loc['populacao'] = loc['populacao'].round().astype('Int64')
    loc['capital'] = loc['capital'].astype('boolean')
    return loc.sort_values('codigo_ibge').reset_index(drop=True)


def limpar_produtos(bruto, etapas):
    df = bruto.copy()
    for col in ['produto_id', 'nome', 'categoria']:
        df[col] = df[col].str.strip()
    df['preco'], df['custo'] = para_numero(df['preco']), para_numero(df['custo'])
    antes = len(df)
    df = df[(df['preco'] > 0) & (df['custo'] > 0)].drop_duplicates('produto_id')
    etapas.registrar('produtos', 'catálogo válido', antes, len(df), 'Achata o JSON e remove produto repetido ou sem preço e custo')
    return df[['produto_id', 'nome', 'categoria', 'preco', 'custo']].reset_index(drop=True)


def limpar_clientes(bruto, localidades, etapas):
    """Uma linha por cliente, com a cidade trocada pelo código do município do IBGE."""
    df = bruto.copy()
    df['cliente_id'] = pd.to_numeric(df['cliente_id'], errors='coerce')
    df['nome'] = df['nome'].str.split().str.join(' ').str.title()
    df['email'] = df['email'].str.strip().str.lower()
    df['segmento'] = padronizar(df['segmento'], config.SEGMENTOS)
    df['data_cadastro'] = para_data(df['data_cadastro'])
    df['data_nascimento'] = para_data(df['data_nascimento'])

    # o mesmo cliente aparece mais de uma vez na planilha: fica a linha mais completa
    antes = len(df)
    df['preenchidos'] = df.notna().sum(axis=1)
    df = df.sort_values(['cliente_id', 'preenchidos'], ascending=[True, False], kind='stable').drop_duplicates('cliente_id')
    etapas.registrar('clientes', 'sem duplicatas', antes, len(df), 'Mantém uma linha por cliente_id (a mais completa)')

    antes = len(df)
    df = df.dropna(subset=['cliente_id', 'nome', 'segmento', 'data_cadastro'])
    df = df[df['data_cadastro'] <= config.HOJE]
    etapas.registrar('clientes', 'sem inválidos', antes, len(df), 'Remove cliente sem id, nome, segmento ou data de cadastro válida')

    # nascimento que daria menos de 16 ou mais de 100 anos vira nulo (o modelo trata o ausente depois)
    idade = (config.HOJE - df['data_nascimento']).dt.days / 365.25
    df['data_nascimento'] = df['data_nascimento'].where(idade.between(16, 100))

    mapa = localidades.assign(chave=chave_municipio(localidades['municipio'], localidades['uf'])).set_index('chave')['codigo_ibge']
    df['codigo_ibge'] = chave_municipio(df['cidade'], df['uf']).map(mapa).astype('Int64')
    sem_local = int(df['codigo_ibge'].isna().sum())
    etapas.registrar('clientes', 'município do IBGE', len(df), len(df),
                     f'Troca cidade + UF pelo código do IBGE: {sem_local} clientes sem cidade ficam com localidade nula')

    df['cliente_id'] = df['cliente_id'].astype(int)
    colunas = ['cliente_id', 'nome', 'email', 'data_nascimento', 'segmento', 'data_cadastro', 'codigo_ibge']
    return df[colunas].sort_values('cliente_id').reset_index(drop=True)


# ========= fato =========
def limpar_compras(bruto, clientes, produtos, etapas):
    """Compras válidas, com cliente e produto existentes nas dimensões e preço coerente com o catálogo."""
    fonte = 'compras'
    df = bruto.drop_duplicates().copy()
    etapas.registrar(fonte, 'sem duplicatas', len(bruto), len(df), 'Remove linhas repetidas')

    df['produto_id'] = df['produto_id'].str.strip().str.upper()
    df['canal'] = padronizar(df['canal'], config.CANAIS)
    df['pagamento'] = df['pagamento'].str.strip().fillna('Não informado')
    df['valor'] = para_numero(df['valor'])
    df['data_compra'] = para_data(df['data_compra'])
    for col in ['id_compra', 'cliente_id', 'quantidade']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    antes = len(df)
    df = df.dropna(subset=['id_compra', 'cliente_id', 'data_compra', 'valor', 'canal'])
    df = df[(df['data_compra'] <= config.HOJE) & (df['valor'] > 0) & df['quantidade'].between(1, 20)]
    etapas.registrar(fonte, 'sem inválidos', antes, len(df),
                     'Remove compra sem cliente, data ou valor, com data impossível ou futura, valor negativo ou quantidade fora de 1 a 20')

    antes = len(df)
    df = df[df['cliente_id'].isin(clientes['cliente_id']) & df['produto_id'].isin(produtos['produto_id'])]
    etapas.registrar(fonte, 'integridade referencial', antes, len(df), 'Remove compra de cliente fora do cadastro ou de produto fora do catálogo')

    # outlier: com o catálogo em mãos, o preço unitário é comparado com o preço de tabela do próprio produto
    antes = len(df)
    df = df.merge(produtos[['produto_id', 'preco', 'custo']], on='produto_id', validate='many_to_one')
    relacao = df['valor'] / df['quantidade'] / df['preco']
    df = df[relacao.between(PRECO_MIN, PRECO_MAX)]
    etapas.registrar(fonte, 'sem outliers de preço', antes, len(df),
                     f'Remove compra com preço unitário fora de {PRECO_MIN:.0%} a {PRECO_MAX:.0%} do preço de tabela')

    df['custo_total'] = (df['custo'] * df['quantidade']).round(2)
    for col in ['id_compra', 'cliente_id', 'quantidade']:
        df[col] = df[col].astype(int)
    colunas = ['id_compra', 'cliente_id', 'produto_id', 'data_compra', 'quantidade', 'valor', 'custo_total', 'canal', 'pagamento']
    df = df[colunas].sort_values('id_compra').reset_index(drop=True)
    assert df['id_compra'].is_unique and df.notna().all().all()
    return df


def montar_datas(compras):
    """Calendário contínuo do primeiro ao último dia com compra."""
    dias = pd.date_range(compras['data_compra'].min(), compras['data_compra'].max(), freq='D')
    return pd.DataFrame({
        'data': dias, 'ano': dias.year, 'trimestre': dias.quarter, 'mes': dias.month,
        'nome_mes': [MESES[m - 1] for m in dias.month], 'dia_semana': dias.dayofweek,
        'nome_dia': [DIAS[d] for d in dias.dayofweek], 'fim_de_semana': dias.dayofweek >= 5,
    })


def transformar(fontes):
    """Fontes brutas -> ({tabela do dw: DataFrame}, contagem por etapa)."""
    etapas = Etapas()
    localidades = montar_localidades(fontes['municipios_ibge'], fontes['cidades_kaggle'], etapas)
    produtos = limpar_produtos(fontes['produtos'], etapas)
    clientes = limpar_clientes(fontes['clientes'], localidades, etapas)
    compras = limpar_compras(fontes['compras'], clientes, produtos, etapas)
    tabelas = {
        'dim_localidade': localidades, 'dim_cliente': clientes, 'dim_produto': produtos,
        'dim_data': montar_datas(compras), 'fato_compras': compras,
    }
    return tabelas, etapas.tabela()
