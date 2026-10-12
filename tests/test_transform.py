"""Testes das regras de limpeza e integração (não precisam de banco nem de rede)."""
import pandas as pd
import pytest

from src import transform as t


def test_para_numero_aceita_formato_brasileiro():
    serie = pd.Series(['1299.9', 'R$ 1.299,90', ' 59,90 ', 'abc', None])
    assert t.para_numero(serie).tolist()[:3] == [1299.9, 1299.9, 59.9]
    assert t.para_numero(serie).isna().tolist() == [False, False, False, True, True]


def test_para_data_aceita_dois_formatos_e_rejeita_data_impossivel():
    datas = t.para_data(pd.Series(['2025-03-01', '01/03/2025', '2025-02-30', 'sem data', None]))
    assert datas[0] == datas[1] == pd.Timestamp('2025-03-01')
    assert datas[2:].isna().all()


@pytest.mark.parametrize('sujo', ['  OURO ', 'ouro', 'Ouro  '])
def test_padronizar_corrige_caixa_e_espacos(sujo):
    assert t.padronizar(pd.Series([sujo]), ['Bronze', 'Prata', 'Ouro'])[0] == 'Ouro'


def test_padronizar_ignora_acento_e_anula_o_que_nao_reconhece():
    resultado = t.padronizar(pd.Series(['LOJA FISICA', 'telefone', None]), ['Loja Física', 'Site', 'App'])
    assert resultado[0] == 'Loja Física' and resultado[1:].isna().all()


@pytest.fixture
def localidades():
    ibge = pd.DataFrame({
        'municipio-id': ['1600303', '1600600', '2928109'], 'municipio-nome': ['Macapá', 'Santana', 'Santana'],
        'UF-sigla': ['AP', 'AP', 'BA'], 'UF-nome': ['Amapá', 'Amapá', 'Bahia'], 'regiao-nome': ['Norte', 'Norte', 'Nordeste'],
    })
    kaggle = pd.DataFrame({
        'CITY': ['Macapá', 'Santana'], 'STATE': ['AP', 'BA'], 'CAPITAL': ['1', '0'], 'IBGE_RES_POP': ['398204', '24750'],
        'ESTIMATED_POP': ['493634', None], 'IDHM': ['0.733', '0.608'], 'GDP_CAPITA': ['19935.32', '0'],
    })
    return t.montar_localidades(ibge, kaggle, t.Etapas()).set_index('codigo_ibge')


def test_localidades_juntam_ibge_e_kaggle_por_nome_e_uf(localidades):
    assert localidades.loc[1600303, 'idhm'] == 0.733 and localidades.loc[1600303, 'capital']
    assert localidades.loc[2928109, 'idhm'] == 0.608          # Santana da Bahia, não a do Amapá
    assert pd.isna(localidades.loc[1600600, 'idhm'])          # município sem indicador continua na dimensão


def test_localidades_usam_populacao_do_censo_quando_falta_a_estimada_e_anulam_pib_zerado(localidades):
    assert localidades.loc[2928109, 'populacao'] == 24750
    assert pd.isna(localidades.loc[2928109, 'pib_per_capita'])


def test_clientes_ficam_com_uma_linha_e_codigo_do_ibge(localidades):
    bruto = pd.DataFrame({
        'cliente_id': ['1', '1', '2', '3'], 'nome': ['ana  SILVA', 'Ana Silva', 'Bruno Lima', 'Carla Góes'],
        'email': [None, ' ANA@EMAIL.COM ', 'bruno@email.com', 'carla@email.com'],
        'data_nascimento': ['1990-05-10', '10/05/1990', '1900-01-01', None],
        'cidade': [None, ' MACAPA ', 'santana', None], 'uf': [None, 'ap', 'BA', None],
        'segmento': ['ouro', 'Ouro', 'PRATA ', 'Bronze'], 'data_cadastro': ['2025-01-01', '01/01/2025', '2025-02-01', '2025-03-01'],
    })
    etapas = t.Etapas()
    clientes = t.limpar_clientes(bruto, localidades.reset_index(), etapas).set_index('cliente_id')

    assert len(clientes) == 3 and etapas.tabela().loc[0, 'removidos'] == 1
    assert clientes.loc[1, ['nome', 'email', 'segmento']].tolist() == ['Ana Silva', 'ana@email.com', 'Ouro']
    assert clientes.loc[1, 'codigo_ibge'] == 1600303 and clientes.loc[2, 'codigo_ibge'] == 2928109
    assert pd.isna(clientes.loc[2, 'data_nascimento'])        # 126 anos: nascimento impossível
    assert pd.isna(clientes.loc[3, 'codigo_ibge'])            # sem cidade continua no cadastro


def test_compras_removem_duplicata_invalido_orfao_e_outlier():
    clientes = pd.DataFrame({'cliente_id': [1, 2]})
    produtos = pd.DataFrame({'produto_id': ['P001'], 'preco': [100.0], 'custo': [60.0]})
    linhas = [
        ('1', '1', 'P001', '2025-01-10', '2', '190.00', 'Site', 'Pix'),             # válida
        ('1', '1', 'P001', '2025-01-10', '2', '190.00', 'Site', 'Pix'),             # duplicata
        ('2', '2', 'p001', '15/01/2025', '1', 'R$ 95,00', ' LOJA FISICA', None),    # válida depois da limpeza
        ('3', '1', 'P001', '2025-02-30', '1', '95.00', 'App', 'Pix'),               # data impossível
        ('4', '1', 'P001', '2025-01-11', '1', '-95.00', 'App', 'Pix'),              # valor negativo
        ('5', '1', 'P001', '2025-01-11', '999', '95.00', 'App', 'Pix'),             # quantidade inválida
        ('6', '9001', 'P001', '2025-01-12', '1', '95.00', 'App', 'Pix'),            # cliente fora do cadastro
        ('7', '1', 'P999', '2025-01-12', '1', '95.00', 'App', 'Pix'),               # produto fora do catálogo
        ('8', '1', 'P001', '2025-01-13', '1', '9500.00', 'App', 'Pix'),             # outlier: 95 vezes o preço de tabela
        ('9', '1', 'P001', '2031-01-15', '1', '95.00', 'App', 'Pix'),               # data no futuro
    ]
    bruto = pd.DataFrame(linhas, columns=['id_compra', 'cliente_id', 'produto_id', 'data_compra', 'quantidade', 'valor', 'canal', 'pagamento'])
    etapas = t.Etapas()
    compras = t.limpar_compras(bruto, clientes, produtos, etapas)

    assert compras['id_compra'].tolist() == [1, 2]
    assert compras.loc[1, ['valor', 'canal', 'pagamento', 'custo_total']].tolist() == [95.0, 'Loja Física', 'Não informado', 60.0]
    assert compras.loc[0, 'custo_total'] == 120.0
    assert etapas.tabela()['removidos'].tolist() == [1, 4, 2, 1]


def test_calendario_e_continuo_e_marca_fim_de_semana():
    datas = t.montar_datas(pd.DataFrame({'data_compra': pd.to_datetime(['2025-01-03', '2025-01-06'])}))
    assert len(datas) == 4
    assert datas['nome_dia'].tolist() == ['Sexta', 'Sábado', 'Domingo', 'Segunda']
    assert datas['fim_de_semana'].tolist() == [False, True, True, False]
