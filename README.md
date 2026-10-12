# Projeto Integrador: pipeline de dados para previsão de churn

Projeto Integrador da disciplina de Engenharia de Dados. Um pipeline de ponta a ponta para uma loja de artigos
esportivos: coleta cinco fontes, armazena no PostgreSQL em modelo estrela, limpa e integra com um ETL em Python,
cria features por cliente e treina um modelo que prevê quem vai parar de comprar (churn).

**Autora:** Lorena ([@Lorenalgm](https://github.com/Lorenalgm)), projeto individual

```
Fontes de dados  ->  PostgreSQL  ->  ETL Python  ->  Features  ->  Machine Learning  ->  Métricas  ->  Resultados
 CSV, Excel, JSON     staging         extract          29 por         3 modelos +         F1, recall,    modelo .pkl e
 API IBGE, Kaggle     dw (estrela)    transform        cliente        baseline            ROC AUC        tabelas em ml
                      ml              load
```

## Resultado

| Modelo escolhido | F1 | Recall | Precision | ROC AUC | Accuracy |
|---|---|---|---|---|---|
| Regressão Logística | 0,650 | 0,645 | 0,656 | 0,790 | 0,785 |

Métricas no conjunto de teste (200 clientes, 31% de churn). O baseline que sempre responde "não é churn" tem
accuracy de 0,690 e F1 zero. A comparação completa dos modelos está em
[`reports/comparacao_modelos.csv`](reports/comparacao_modelos.csv) e a análise no
[notebook final](notebooks/02_projeto_integrador.ipynb). O relatório com as evidências de execução está em
[`relatorio_projeto_integrador.pdf`](relatorio_projeto_integrador.pdf).

## Fontes de dados

| # | Fonte | Formato | Conteúdo | Origem |
|---|---|---|---|---|
| 1 | Sistema de vendas | CSV (`data/raw/compras.csv`) | 17.592 linhas, uma por compra | fictícia, semente fixa |
| 2 | CRM | Excel (`data/raw/clientes.xlsx`) | 1.545 linhas de cadastro | fictícia, semente fixa |
| 3 | Catálogo | JSON aninhado (`data/raw/produtos.json`) | 25 produtos com preço e custo | fictícia, semente fixa |
| 4 | [API de Localidades do IBGE](https://servicodados.ibge.gov.br/api/docs/localidades) | API REST | 5.571 municípios com UF e região | dado real |
| 5 | [Kaggle: Brazilian Cities](https://www.kaggle.com/datasets/crisparada/brazilian-cities) | CSV via API do Kaggle | população, IDHM e PIB per capita por município | dado real, CC BY-SA 4.0 |

As três primeiras simulam os sistemas internos da loja e chegam sujas de propósito (duplicatas, datas em dois
formatos, valores como texto, ausentes, outliers e chaves que não existem nas outras fontes). São geradas por
`src/gerar_dados.py`. As duas últimas são dados públicos reais e enriquecem o cadastro, que só tem o nome da cidade.

A resposta da API do IBGE e o CSV do Kaggle ficam versionados em `data/raw/`. O pipeline consulta a API do IBGE a
cada execução e só usa a cópia em disco se a API não responder. O arquivo do Kaggle só é baixado se não existir,
então **não é preciso ter conta no Kaggle para reproduzir**.

## Modelagem no PostgreSQL

Três schemas, criados por [`sql/schema.sql`](sql/schema.sql):

- **`staging`**: cada fonte como chegou, tudo em texto. Dá rastreabilidade ao que a limpeza rejeitou.
- **`dw`**: modelo estrela com os dados limpos e integrados, com chaves primárias e estrangeiras, `CHECK` nas regras
  de negócio e índices nas chaves do fato. Inclui `etl_etapas` (trilha de auditoria da limpeza) e a visão `vw_compras`.
- **`ml`**: `features_cliente`, `metricas_modelo` e `previsoes_teste`.

```mermaid
erDiagram
    dim_localidade ||--o{ dim_cliente : "codigo_ibge"
    dim_cliente ||--o{ fato_compras : "cliente_id"
    dim_produto ||--o{ fato_compras : "produto_id"
    dim_data ||--o{ fato_compras : "data_compra"

    fato_compras {
        int id_compra PK
        int cliente_id FK
        text produto_id FK
        date data_compra FK
        smallint quantidade
        numeric valor
        numeric custo_total
        text canal
        text pagamento
    }
    dim_cliente {
        int cliente_id PK
        text nome
        text email
        date data_nascimento
        text segmento
        date data_cadastro
        int codigo_ibge FK
    }
    dim_produto {
        text produto_id PK
        text nome
        text categoria
        numeric preco
        numeric custo
    }
    dim_localidade {
        int codigo_ibge PK
        text municipio
        char uf
        text estado
        text regiao
        boolean capital
        int populacao
        numeric idhm
        numeric pib_per_capita
    }
    dim_data {
        date data PK
        smallint ano
        smallint trimestre
        smallint mes
        text nome_mes
        smallint dia_semana
        text nome_dia
        boolean fim_de_semana
    }
```

`dim_localidade` vem da API do IBGE (município, UF, região) com as colunas `capital`, `populacao`, `idhm` e
`pib_per_capita` vindas do Kaggle.

## Como executar

Pré-requisitos: Python 3.12 e um PostgreSQL (local ou pelo Docker).

```bash
git clone https://github.com/Lorenalgm/projeto-integrador-engenharia-dados.git
cd projeto-integrador-engenharia-dados

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

.venv/bin/python -m src.pipeline          # roda tudo: fontes -> PostgreSQL -> features -> modelo -> métricas
```

O banco padrão é `postgresql+psycopg2://localhost/projeto_integrador` (PostgreSQL local, usuário do sistema, sem
senha). O banco é criado automaticamente se não existir. Para usar outro, defina `DATABASE_URL`.

**Sem PostgreSQL instalado**, use o `docker-compose.yml` do repositório:

```bash
docker compose up -d
export DATABASE_URL=postgresql+psycopg2://aluno:aluno@localhost:5433/projeto_integrador
.venv/bin/python -m src.pipeline
```

Outros comandos:

```bash
.venv/bin/python -m src.pipeline --gerar-dados    # recria antes as fontes fictícias (o resultado é sempre o mesmo)
.venv/bin/python -m src.pipeline --so-etl         # para depois da carga no PostgreSQL
.venv/bin/python -m pytest                        # testes das regras de limpeza (não precisam de banco)
psql -d projeto_integrador -f sql/verificacao.sql # verificação da carga e consultas analíticas
.venv/bin/jupyter lab                             # abrir os notebooks da pasta notebooks/
```

Para executar os notebooks sem abrir o Jupyter:

```bash
cd notebooks
../.venv/bin/jupyter nbconvert --to notebook --execute --inplace 01_analise_exploratoria.ipynb 02_projeto_integrador.ipynb
```

O pipeline leva cerca de 10 segundos e grava o log em `logs/pipeline.log`. Com a mesma semente, os números são
sempre os mesmos.

## Organização do repositório

```
├── data/raw/                  fontes brutas (CSV, Excel, JSON, resposta do IBGE, CSV do Kaggle)
├── sql/
│   ├── schema.sql             schemas, tabelas, restrições, índices e visão
│   └── verificacao.sql        conferência da carga e consultas analíticas
├── src/
│   ├── config.py              caminhos, URL do banco e regras de negócio (data de corte, janelas)
│   ├── gerar_dados.py         simula a loja e grava as três fontes fictícias
│   ├── extract.py             lê as cinco fontes (arquivos, API do IBGE, API do Kaggle)
│   ├── transform.py           limpeza, integração e contagem de linhas por etapa
│   ├── load.py                cria o banco, carrega staging e dw e verifica a carga
│   ├── features.py            target, features por cliente e documentação das features
│   ├── model.py               treino, validação cruzada, comparação, avaliação e gravação
│   ├── graficos.py            estilo dos gráficos dos notebooks
│   └── pipeline.py            orquestra todas as etapas
├── notebooks/
│   ├── 01_analise_exploratoria.ipynb    EDA lendo do PostgreSQL
│   └── 02_projeto_integrador.ipynb      notebook final: pipeline completo, modelo e conclusões
├── tests/test_transform.py    testes das regras de limpeza e integração
├── models/modelo_churn.pkl    Pipeline treinado (imputação + padronização + classificador)
├── reports/                   métricas, comparações, documentação das features e figuras
├── evidencias/                saídas reais de execução e prints
├── relatorio/                 script que monta o relatório em PDF a partir dos arquivos acima
└── docker-compose.yml         PostgreSQL para reprodução
```

## Etapas do pipeline

### 1. Extract (`src/extract.py`)

Lê tudo como texto, sem tratar nada. O JSON aninhado é achatado com `json_normalize`. A API do IBGE tem três
tentativas com espera crescente e a resposta é guardada em disco.

### 2. Transform (`src/transform.py`)

| Fonte | Etapa | Entraram | Removidos | Restaram |
|---|---|---|---|---|
| clientes | sem duplicatas (fica a linha mais completa de cada cliente) | 1.545 | 45 | 1.500 |
| compras | sem duplicatas | 17.592 | 512 | 17.080 |
| compras | sem inválidos (sem cliente, data ou valor; data impossível ou futura; valor negativo) | 17.080 | 732 | 16.348 |
| compras | integridade referencial (cliente fora do cadastro, produto fora do catálogo) | 16.348 | 99 | 16.249 |
| compras | sem outliers de preço | 16.249 | 157 | 16.092 |

Decisões técnicas:

- **Outliers pelo catálogo, não por estatística.** O preço unitário pago é comparado com o preço de tabela do
  próprio produto (aceito de 50% a 110%). A loja vende de protetor bucal (R$ 24,90) a estação de musculação
  (R$ 3.499,00); um limite único para a coluna `valor` trataria produto caro como erro.
- **Essenciais são removidos, não preenchidos.** Compra sem cliente, data ou valor não entra.
- **Não essenciais ficam nulos no banco.** Nascimento inválido e cidade ausente não são inventados no ETL. A
  imputação fica no Pipeline do modelo, que calcula a mediana só com o treino.
- **Integração por nome + UF.** Cidade e UF do cliente viram o código do município do IBGE. O Kaggle não traz esse
  código, então a junção usa nome sem acento + UF (necessário porque existe Santana no Amapá e na Bahia).
  5.551 dos 5.571 municípios ficaram com IDHM.

### 3. Load (`src/load.py`)

Carga completa: recria os schemas, grava o bruto em `staging` e o limpo em `dw` em uma única transação. No fim,
confere no próprio banco contagens, receita e junções.

### 4. Features (`src/features.py`)

- **Target.** `churn = 1` se o cliente não comprou nos 90 dias depois da data de corte (31/03/2026).
- **Sem vazamento.** As features usam só as compras até o corte.
- **Base.** 999 clientes ativos (compraram nos 180 dias antes do corte), 30,8% de churn.

| Grupo | Features | Fonte |
|---|---|---|
| Cadastro | `idade`, `segmento_cod` (ordinal) | Excel |
| Temporais | `dias_desde_cadastro`, `dias_sem_comprar`, `intervalo_medio_dias`, `atraso_relativo`, `pct_compras_fim_de_semana` | CSV, Excel |
| Agregações | `qtd_compras`, `total_gasto`, `ticket_medio`, `categorias_distintas`, `margem_pct`, `pct_compras_online`, `qtd_compras_90d`, `gasto_90d`, `tendencia_compras`, `compras_por_mes` | CSV, JSON |
| Encoding | `canal_*` (one-hot, 3 colunas), `regiao_*` (one-hot, 5 colunas) | CSV, API IBGE |
| Localidade | `capital`, `populacao_log`, `idhm`, `pib_per_capita` | Kaggle |

São 29 colunas. A descrição de cada uma está em
[`reports/documentacao_features.csv`](reports/documentacao_features.csv).

### 5. Modelo e avaliação (`src/model.py`)

Três classificadores e um baseline, todos em um `Pipeline` do scikit-learn (imputação pela mediana, padronização e
classificador). Divisão 80/20 estratificada. A escolha usa o F1 médio da validação cruzada (5 dobras, só no treino);
o teste fica para a avaliação final.

| Modelo | F1 (CV) | Accuracy | Precision | Recall | F1 | ROC AUC |
|---|---|---|---|---|---|---|
| **Regressão Logística** | 0,601 | 0,785 | 0,656 | 0,645 | 0,650 | 0,790 |
| Random Forest | 0,599 | 0,785 | 0,721 | 0,500 | 0,590 | 0,789 |
| Gradient Boosting | 0,555 | 0,760 | 0,750 | 0,339 | 0,467 | 0,728 |
| Baseline (classe majoritária) | 0,000 | 0,690 | 0,000 | 0,000 | 0,000 | 0,500 |

A métrica principal é o F1 da classe churn, porque a accuracy engana com classes desbalanceadas.

## Resultados e análise

- **O modelo encontra 40 dos 62 churns do teste** (recall 0,645) e acerta 40 dos 61 alertas (precision 0,656).
- **O ranking de risco funciona.** Na faixa de risco alto, 69% dos clientes realmente saíram; na de risco baixo, 15%.
- **Recência e atividade recente dominam.** `dias_sem_comprar` e `qtd_compras_90d` são as features mais importantes.
- **Regressão Logística e Random Forest empataram** na validação cruzada (0,601 e 0,599, com desvio de 0,043). Entre
  dois modelos empatados, ficou o mais simples.
- **As fontes externas não melhoraram a previsão.** Sem as features de localidade, o F1 da validação cruzada é
  0,596; com elas, 0,601. A diferença é menor que o desvio entre dobras. O valor da integração ficou na análise
  (receita, margem e churn por região), não no modelo.

**Limitações.** Compras, clientes e catálogo são simulados, com premissas de abandono definidas em
`src/gerar_dados.py`; só o IBGE e o Kaggle são dados reais. O abandono simulado tem um componente aleatório grande,
o que limita o teto de qualquer modelo. São apenas 30 cidades com clientes e a avaliação usa uma única data de corte.

## Créditos dos dados

- IBGE, API de Localidades: https://servicodados.ibge.gov.br/api/docs/localidades
- *Brazilian Cities* (usuário crisparada), Kaggle, licença CC BY-SA 4.0:
  https://www.kaggle.com/datasets/crisparada/brazilian-cities
