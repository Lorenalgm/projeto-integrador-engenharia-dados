"""Gera as três fontes fictícias (e propositalmente sujas) de uma loja de artigos esportivos.

    data/raw/compras.csv     uma linha por compra (sistema de vendas)
    data/raw/clientes.xlsx   cadastro de clientes (planilha do CRM)
    data/raw/produtos.json   catálogo aninhado por categoria, com preço e custo

O comportamento é simulado por cliente: cada um tem um ritmo de compras e uma data em que abandona a
loja, o que dá ao modelo de churn um padrão real para aprender. As premissas da simulação (quem compra
mais e quem abandona mais) estão nas constantes RITMO_* e RISCO_* abaixo.

    python -m src.gerar_dados
"""
import json

import numpy as np
import pandas as pd

from src.config import CANAIS, CLIENTES_XLSX, COMPRAS_CSV, HOJE, PAGAMENTOS, PRODUTOS_JSON, RAW, SEED, SEGMENTOS

N_CLIENTES = 1500
INICIO = pd.Timestamp('2025-01-01')   # primeira compra possível
FIM = HOJE                            # última compra possível

# categoria -> [(produto, preço unitário)]
CATALOGO = {
    'Futebol': [('Chuteira Society', 289.90), ('Bola de Campo Oficial', 159.90),
                ('Camisa de Time', 249.90), ('Caneleira', 49.90)],
    'Corrida': [('Tênis de Corrida', 499.90), ('Relógio GPS', 1299.00),
                ('Shorts Dry Fit', 79.90), ('Cinto de Hidratação', 119.90)],
    'Musculação': [('Par de Halteres 10kg', 219.90), ('Banco Regulável', 649.00),
                   ('Luva de Treino', 59.90), ('Estação de Musculação', 3499.00)],
    'Natação': [('Óculos de Natação', 89.90), ('Touca de Silicone', 29.90),
                ('Sunga de Competição', 139.90)],
    'Ciclismo': [('Bicicleta Aro 29', 2899.00), ('Capacete', 199.90),
                 ('Luva de Ciclismo', 69.90), ('Bermuda Acolchoada', 159.90)],
    'Basquete': [('Bola de Basquete', 179.90), ('Tênis Cano Alto', 599.90),
                 ('Regata de Jogo', 99.90)],
    'Lutas': [('Kimono Jiu-Jitsu', 389.90), ('Luva de Boxe', 229.90),
              ('Protetor Bucal', 24.90)],
}
PRODUTOS = [(f'P{i:03d}', nome, cat, preco) for i, (cat, nome, preco) in enumerate(
    ((cat, nome, preco) for cat, itens in CATALOGO.items() for nome, preco in itens), start=1)]
CATEGORIAS = list(CATALOGO)

# (cidade, UF, região, peso). A loja nasceu em Macapá, por isso o Norte concentra a base de clientes.
CIDADES = [
    ('Macapá', 'AP', 'Norte', 0.20), ('Santana', 'AP', 'Norte', 0.05), ('Belém', 'PA', 'Norte', 0.08),
    ('Manaus', 'AM', 'Norte', 0.06), ('Porto Velho', 'RO', 'Norte', 0.015), ('Rio Branco', 'AC', 'Norte', 0.01),
    ('Boa Vista', 'RR', 'Norte', 0.01), ('Palmas', 'TO', 'Norte', 0.005),
    ('Fortaleza', 'CE', 'Nordeste', 0.04), ('Recife', 'PE', 'Nordeste', 0.04), ('Salvador', 'BA', 'Nordeste', 0.04),
    ('São Luís', 'MA', 'Nordeste', 0.02), ('Natal', 'RN', 'Nordeste', 0.015), ('João Pessoa', 'PB', 'Nordeste', 0.015),
    ('Maceió', 'AL', 'Nordeste', 0.01), ('Teresina', 'PI', 'Nordeste', 0.01), ('Aracaju', 'SE', 'Nordeste', 0.01),
    ('Brasília', 'DF', 'Centro-Oeste', 0.04), ('Goiânia', 'GO', 'Centro-Oeste', 0.02),
    ('Cuiabá', 'MT', 'Centro-Oeste', 0.01), ('Campo Grande', 'MS', 'Centro-Oeste', 0.01),
    ('São Paulo', 'SP', 'Sudeste', 0.08), ('Rio de Janeiro', 'RJ', 'Sudeste', 0.06),
    ('Belo Horizonte', 'MG', 'Sudeste', 0.04), ('Campinas', 'SP', 'Sudeste', 0.015), ('Vitória', 'ES', 'Sudeste', 0.01),
    ('Curitiba', 'PR', 'Sul', 0.03), ('Porto Alegre', 'RS', 'Sul', 0.03), ('Florianópolis', 'SC', 'Sul', 0.015),
    ('Joinville', 'SC', 'Sul', 0.01),
]
PESO_CIDADES = np.array([c[3] for c in CIDADES]) / sum(c[3] for c in CIDADES)

NOMES = ['Ana', 'Bruno', 'Carla', 'Daniel', 'Eduarda', 'Felipe', 'Gabriela', 'Henrique', 'Isabela', 'João',
         'Karina', 'Lucas', 'Mariana', 'Nicolas', 'Olívia', 'Paulo', 'Rafaela', 'Samuel', 'Tatiane', 'Vitor',
         'Aline', 'Caio', 'Débora', 'Elias', 'Fernanda', 'Gustavo', 'Helena', 'Igor', 'Juliana', 'Leonardo']
SOBRENOMES = ['Silva', 'Santos', 'Oliveira', 'Souza', 'Rodrigues', 'Ferreira', 'Alves', 'Pereira', 'Lima', 'Gomes',
              'Costa', 'Ribeiro', 'Martins', 'Carvalho', 'Almeida', 'Lopes', 'Soares', 'Barbosa', 'Monteiro', 'Góes']

# premissas da simulação: efeito de cada atributo no ritmo de compras e no risco mensal de abandono
RITMO_SEG = {'Bronze': 1.0, 'Prata': 1.25, 'Ouro': 1.6}
RISCO_SEG = {'Bronze': 1.35, 'Prata': 1.0, 'Ouro': 0.55}
RISCO_CANAL = {'Loja Física': 1.2, 'Site': 1.0, 'App': 0.75}
# quanto mais longe do centro de distribuição (Macapá), maior o prazo de entrega e o abandono
RISCO_REGIAO = {'Norte': 0.8, 'Nordeste': 1.0, 'Centro-Oeste': 1.15, 'Sudeste': 1.25, 'Sul': 1.4}
RISCO_BASE = 0.05


def sem_acento(texto):
    return texto.translate(str.maketrans('áãâéêíóôõúç', 'aaaeeiooouc'))


def baguncar(rng, texto):
    """Devolve o texto com caixa, espaços ou acentos inconsistentes."""
    return str(rng.choice([texto.upper(), texto.lower(), f'  {texto} ', f'{texto}  ',
                           sem_acento(texto), sem_acento(texto).upper()]))


def br(data):
    return pd.Timestamp(data).strftime('%d/%m/%Y')


def simular(rng):
    """Devolve (clientes, compras) ainda limpos."""
    clientes, compras = [], []
    for c in range(1, N_CLIENTES + 1):
        cadastro = pd.Timestamp('2024-01-01') + pd.Timedelta(days=int(rng.integers(0, 790)))
        idade = 0
        while not 18 <= idade <= 75:
            idade = int(rng.normal(37, 12))
        nascimento = cadastro - pd.Timedelta(days=int(idade * 365.25 + rng.integers(0, 365)))
        cidade, uf, regiao, _ = CIDADES[rng.choice(len(CIDADES), p=PESO_CIDADES)]
        segmento = str(rng.choice(SEGMENTOS, p=[0.55, 0.30, 0.15]))
        canal_pref = str(rng.choice(CANAIS, p=[0.40, 0.35, 0.25]))
        cat_pref = str(rng.choice(CATEGORIAS))
        clientes.append({
            'cliente_id': c, 'nome': f'{rng.choice(NOMES)} {rng.choice(SOBRENOMES)}',
            'email': f'cliente{c:04d}@email.com', 'data_nascimento': nascimento.strftime('%Y-%m-%d'),
            'cidade': cidade, 'uf': uf, 'segmento': segmento, 'data_cadastro': cadastro.strftime('%Y-%m-%d'),
        })

        ritmo = rng.lognormal(np.log(0.85), 0.55) * RITMO_SEG[segmento]      # compras por mês
        risco = (RISCO_BASE * RISCO_SEG[segmento] * RISCO_CANAL[canal_pref] * RISCO_REGIAO[regiao]
                 * (1.3 if idade < 25 else 1.0))
        comeco = max(cadastro, INICIO)
        abandono = comeco + pd.Timedelta(days=float(rng.exponential(30 / risco)))
        limite = min(abandono, FIM)

        # cliente novo compra logo depois do cadastro; cliente antigo já está no ritmo dele
        espera = 10 if cadastro >= INICIO else 30 / ritmo
        dia = comeco + pd.Timedelta(days=float(rng.exponential(espera)))
        while dia <= limite:
            cat = cat_pref if rng.random() < 0.55 else str(rng.choice(CATEGORIAS))
            opcoes = [p for p in PRODUTOS if p[2] == cat]
            pid, _, _, preco = opcoes[rng.integers(len(opcoes))]
            qtd = int(rng.choice([1, 2, 3], p=[0.72, 0.21, 0.07]))
            desconto = rng.uniform(0, 0.15)   # promoções: até 15% abaixo do preço de tabela
            compras.append({
                'cliente_id': c, 'produto_id': pid, 'data_compra': dia.strftime('%Y-%m-%d'), 'quantidade': qtd,
                'valor': round(preco * qtd * (1 - desconto), 2),
                'canal': canal_pref if rng.random() < 0.75 else str(rng.choice(CANAIS)),
                'pagamento': str(rng.choice(PAGAMENTOS, p=[0.4, 0.35, 0.15, 0.1])),
            })
            dia += pd.Timedelta(days=float(rng.exponential(30 / ritmo)))

    compras = pd.DataFrame(compras).sort_values('data_compra', kind='stable').reset_index(drop=True)
    compras.insert(0, 'id_compra', range(1, len(compras) + 1))
    return pd.DataFrame(clientes), compras


class Sujeira:
    """Sorteia linhas para sujar e guarda a contagem do que foi injetado."""

    def __init__(self, rng, df, fonte):
        self.rng, self.df, self.fonte, self.injetado = rng, df.astype(object), fonte, {}

    def sorteia(self, nome, fracao):
        idx = self.rng.choice(len(self.df), size=int(len(self.df) * fracao), replace=False)
        self.injetado[f'{self.fonte}: {nome}'] = len(idx)
        return idx

    def duplicar(self, fracao):
        dup = self.df.iloc[self.sorteia('linhas duplicadas', fracao)]
        return pd.concat([self.df, dup]).sample(frac=1, random_state=SEED).reset_index(drop=True)


def sujar_clientes(rng, clientes):
    s = Sujeira(rng, clientes, 'clientes')
    df = s.df
    for col, fracao in [('cidade', 0.15), ('segmento', 0.08), ('nome', 0.06)]:
        for i in s.sorteia(f'{col} com texto inconsistente', fracao):
            df.at[i, col] = baguncar(rng, df.at[i, col])
    for i in s.sorteia('uf em minúsculas ou com espaços', 0.06):
        df.at[i, 'uf'] = str(rng.choice([df.at[i, 'uf'].lower(), f" {df.at[i, 'uf']} "]))
    for i in s.sorteia('email com maiúsculas ou espaços', 0.10):
        df.at[i, 'email'] = str(rng.choice([df.at[i, 'email'].upper(), f" {df.at[i, 'email']}  "]))
    for col, fracao in [('data_nascimento', 0.08), ('data_cadastro', 0.05)]:
        for i in s.sorteia(f'{col} em DD/MM/AAAA', fracao):
            df.at[i, col] = br(df.at[i, col])
    for i in s.sorteia('data_nascimento impossível', 0.01):
        df.at[i, 'data_nascimento'] = str(rng.choice(['1900-01-01', '2031-05-20', '0000-00-00', 'não informado']))
    for i in s.sorteia('cidade e uf ausentes', 0.03):
        df.at[i, 'cidade'] = df.at[i, 'uf'] = None
    for col, fracao in [('data_nascimento', 0.04), ('email', 0.02)]:
        df.loc[s.sorteia(f'{col} ausente', fracao), col] = None
    return s.duplicar(0.03), s.injetado


def sujar_compras(rng, compras):
    s = Sujeira(rng, compras, 'compras')
    df, n = s.df, len(compras)
    for i in s.sorteia('canal com texto inconsistente', 0.05):
        df.at[i, 'canal'] = baguncar(rng, df.at[i, 'canal'])
    for i in s.sorteia('data_compra em DD/MM/AAAA', 0.08):
        df.at[i, 'data_compra'] = br(df.at[i, 'data_compra'])
    for i in s.sorteia('valor como texto (R$ 1.299,90)', 0.04):
        v = f"{df.at[i, 'valor']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        df.at[i, 'valor'] = f'R$ {v}'

    # valores inválidos e outliers (em linhas que ainda têm valor numérico)
    numericas = [i for i in range(n) if not isinstance(df.at[i, 'valor'], str)]
    alvo = rng.choice(numericas, size=int(n * 0.016), replace=False)
    corte = int(n * 0.010)
    for i in alvo[:corte]:
        df.at[i, 'valor'] = round(df.at[i, 'valor'] * int(rng.choice([10, 100])), 2)
    for i in alvo[corte:]:
        df.at[i, 'valor'] = -df.at[i, 'valor']
    s.injetado['compras: valor outlier (x10 ou x100)'] = corte
    s.injetado['compras: valor negativo'] = len(alvo) - corte
    for i in s.sorteia('quantidade inválida (0, -1, 999)', 0.006):
        df.at[i, 'quantidade'] = int(rng.choice([0, -1, 999]))
    for i in s.sorteia('data_compra inválida', 0.005):
        df.at[i, 'data_compra'] = str(rng.choice(['2025-02-30', '00/00/0000', '2025-13-45', 'sem data']))
    for i in s.sorteia('data_compra no futuro', 0.003):
        df.at[i, 'data_compra'] = f'2031-{rng.integers(1, 13):02d}-15'

    # chaves que não existem nas outras fontes
    for i in s.sorteia('cliente_id que não existe no cadastro', 0.003):
        df.at[i, 'cliente_id'] = int(rng.integers(9000, 9999))
    for i in s.sorteia('produto_id que não existe no catálogo', 0.003):
        df.at[i, 'produto_id'] = str(rng.choice(['P999', 'P000', 'X01']))

    for col, fracao in [('pagamento', 0.02), ('valor', 0.015), ('data_compra', 0.005), ('cliente_id', 0.004)]:
        df.loc[s.sorteia(f'{col} ausente', fracao), col] = None
    df = s.duplicar(0.03)
    df['cliente_id'] = df['cliente_id'].astype('Int64')
    return df, s.injetado


def catalogo_json(rng):
    return {
        'loja': 'Amapá Esportes',
        'atualizado_em': HOJE.strftime('%Y-%m-%d'),
        'categorias': [
            {'categoria': cat,
             'produtos': [{'produto_id': pid, 'nome': nome, 'preco': preco,
                           'custo': round(preco * float(rng.uniform(0.45, 0.70)), 2)}
                          for pid, nome, c, preco in PRODUTOS if c == cat]}
            for cat in CATEGORIAS],
    }


def main():
    rng = np.random.default_rng(SEED)
    clientes, compras = simular(rng)
    clientes_sujo, inj_clientes = sujar_clientes(rng, clientes)
    compras_sujo, inj_compras = sujar_compras(rng, compras)

    RAW.mkdir(parents=True, exist_ok=True)
    compras_sujo.to_csv(COMPRAS_CSV, index=False)
    clientes_sujo.to_excel(CLIENTES_XLSX, index=False, sheet_name='clientes')
    PRODUTOS_JSON.write_text(json.dumps(catalogo_json(rng), ensure_ascii=False, indent=2) + '\n')

    print(f'compras.csv:   {len(compras_sujo)} linhas ({len(compras)} compras de '
          f'{compras["cliente_id"].nunique()} clientes antes da sujeira)')
    print(f'clientes.xlsx: {len(clientes_sujo)} linhas ({len(clientes)} clientes antes da sujeira)')
    print(f'produtos.json: {len(PRODUTOS)} produtos em {len(CATEGORIAS)} categorias')
    print('Sujeira injetada:')
    for nome, qtd in {**inj_clientes, **inj_compras}.items():
        print(f'  {qtd:5d}  {nome}')


if __name__ == '__main__':
    main()
