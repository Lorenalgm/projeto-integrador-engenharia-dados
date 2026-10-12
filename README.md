# Projeto Integrador: pipeline de dados para previsão de churn

Pipeline de Engenharia de Dados de ponta a ponta para uma loja de artigos esportivos. Coleta cinco fontes, armazena
no PostgreSQL, limpa e integra com um ETL em Python, cria features por cliente e treina um modelo de classificação
que prevê quem vai parar de comprar.

```
Fontes de dados -> PostgreSQL -> ETL Python -> Features -> Machine Learning -> Métricas -> Resultados
```

## Sumário

1. [Como executar](#como-executar)
2. [Organização do repositório](#organização-do-repositório)
3. [Fontes de dados](#fontes-de-dados)
4. [Modelagem no PostgreSQL](#modelagem-no-postgresql)
5. [ETL](#etl)
6. [Features](#features)
7. [Modelo e métricas](#modelo-e-métricas)
8. [Análise dos resultados](#análise-dos-resultados)
9. [Limitações](#limitações)

## Como executar

Pré-requisitos: Python 3.12 e PostgreSQL.

```bash
git clone https://github.com/Lorenalgm/projeto-integrador-engenharia-dados.git
cd projeto-integrador-engenharia-dados
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

.venv/bin/python -m src.pipeline
```

Esse comando roda tudo em cerca de 10 segundos: lê as fontes, cria o banco `projeto_integrador`, carrega, calcula as
features, treina e grava as métricas. O resultado é sempre o mesmo (semente fixa).

**Banco.** O padrão é o PostgreSQL local sem senha (`postgresql+psycopg2://localhost/projeto_integrador`). Para usar
outro, defina `DATABASE_URL`. Sem PostgreSQL instalado, use o Docker:

```bash
docker compose up -d
export DATABASE_URL=postgresql+psycopg2://aluno:aluno@localhost:5433/projeto_integrador
```

**Outros comandos.**

| Comando | O que faz |
|---|---|
| `.venv/bin/python -m src.pipeline --so-etl` | Para depois da carga no PostgreSQL |
| `.venv/bin/python -m src.pipeline --gerar-dados` | Recria antes as fontes fictícias |
| `.venv/bin/python -m pytest` | Testa as regras de limpeza (sem banco) |
| `psql -d projeto_integrador -f sql/verificacao.sql` | Confere a carga com SQL |
| `.venv/bin/jupyter lab` | Abre os notebooks (rodar o pipeline antes) |

## Organização do repositório

| Caminho | Conteúdo |
|---|---|
| `src/pipeline.py` | Orquestra todas as etapas |
| `src/extract.py`, `transform.py`, `load.py` | ETL em Python |
| `src/features.py` | Target e features por cliente |
| `src/model.py` | Treino, comparação e avaliação dos modelos |
| `src/gerar_dados.py` | Gera as três fontes fictícias |
| `src/config.py`, `src/graficos.py` | Parâmetros do projeto e estilo dos gráficos |
| `sql/schema.sql` | Estrutura do banco (schemas, tabelas, chaves, visão) |
| `sql/verificacao.sql` | Conferência da carga e consultas analíticas |
| `notebooks/01_analise_exploratoria.ipynb` | Análise exploratória, lendo do PostgreSQL |
| `notebooks/02_projeto_integrador.ipynb` | **Notebook final**: pipeline completo, modelo e conclusões |
| `tests/` | Testes das regras de limpeza e integração |
| `data/raw/` | Fontes brutas |
| `models/` | Modelo treinado (`modelo_churn.pkl`) |
| `reports/` | Métricas, comparações, documentação das features e figuras |
| `evidencias/` | Saídas reais de execução e prints |
| `relatorio_projeto_integrador.pdf` | Relatório da entrega (gerado por `relatorio/gerar_relatorio.py`) |

## Fontes de dados

| # | Fonte | Formato | Conteúdo | Origem |
|---|---|---|---|---|
| 1 | Sistema de vendas | CSV | 17.592 linhas de compras | fictícia |
| 2 | CRM | Excel | 1.545 linhas de cadastro de clientes | fictícia |
| 3 | Catálogo | JSON aninhado | 25 produtos com preço e custo | fictícia |
| 4 | [API de Localidades do IBGE](https://servicodados.ibge.gov.br/api/docs/localidades) | API REST | 5.571 municípios com UF e região | real |
| 5 | [Kaggle: Brazilian Cities](https://www.kaggle.com/datasets/crisparada/brazilian-cities) | CSV via API do Kaggle | população, IDHM e PIB per capita | real, CC BY-SA 4.0 |

As fontes fictícias simulam os sistemas da loja e chegam sujas de propósito: duplicatas, datas em dois formatos,
valores como texto, ausentes, outliers e chaves que não existem nas outras fontes. As fontes reais enriquecem o
cadastro, que só tem o nome da cidade.

A API do IBGE é consultada a cada execução (a cópia em `data/raw/` só é usada se ela não responder). O arquivo do
Kaggle já está no repositório, então não é preciso ter conta no Kaggle.

## Modelagem no PostgreSQL

| Schema | Papel |
|---|---|
| `staging` | Cada fonte como chegou, em texto. Permite auditar o que a limpeza rejeitou |
| `dw` | Modelo estrela com os dados limpos, a trilha do ETL (`etl_etapas`) e a visão `vw_compras` |
| `ml` | `features_cliente`, `metricas_modelo` e `previsoes_teste` |

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
        text regiao
        boolean capital
        int populacao
        numeric idhm
        numeric pib_per_capita
    }
    dim_data {
        date data PK
        smallint ano
        smallint mes
        smallint dia_semana
        boolean fim_de_semana
    }
```

As tabelas têm chave primária, chaves estrangeiras, `CHECK` nas regras de negócio e índices nas chaves do fato.
`dim_localidade` junta a API do IBGE (município, UF, região) com o Kaggle (capital, população, IDHM, PIB per capita).

## ETL

**Extract** lê tudo como texto, sem tratar. **Transform** limpa e integra. **Load** recria os schemas, grava o
bruto em `staging` e o limpo em `dw` em uma única transação, e confere contagens, receita e junções no banco.

| Fonte | Etapa da limpeza | Entraram | Removidos | Restaram |
|---|---|---|---|---|
| clientes | duplicatas (fica a linha mais completa) | 1.545 | 45 | 1.500 |
| compras | duplicatas | 17.592 | 512 | 17.080 |
| compras | inválidos (sem cliente, data ou valor; data impossível; valor negativo) | 17.080 | 732 | 16.348 |
| compras | cliente fora do cadastro ou produto fora do catálogo | 16.348 | 99 | 16.249 |
| compras | outliers de preço | 16.249 | 157 | 16.092 |

A mesma contagem fica gravada em `dw.etl_etapas`.

Decisões técnicas:

- **Outliers pelo catálogo.** O preço pago é comparado com o preço de tabela do próprio produto (aceito de 50% a
  110%). Um limite único para a coluna `valor` trataria produto caro como erro: a loja vende de R$ 24,90 a R$ 3.499,00.
- **Dado essencial ausente remove a linha.** Compra sem cliente, data ou valor não é preenchida.
- **Dado não essencial fica nulo.** Nascimento inválido e cidade ausente não são inventados no ETL. O modelo imputa
  a mediana, calculada só com o treino.
- **Integração por nome + UF.** O Kaggle não traz o código do IBGE, então a junção usa nome sem acento + UF
  (existe Santana no Amapá e na Bahia). 5.551 dos 5.571 municípios ficaram com IDHM.

## Features

O churn é definido com uma data de corte (31/03/2026):

- **Target:** `churn = 1` se o cliente não comprou nos 90 dias depois do corte.
- **Features:** usam só as compras até o corte, para não vazar informação do futuro.
- **Base:** 999 clientes ativos (compraram nos 180 dias antes do corte), 30,8% de churn.

| Grupo | Features | Fonte |
|---|---|---|
| Cadastro | `idade`, `segmento_cod` | Excel |
| Temporais | `dias_desde_cadastro`, `dias_sem_comprar`, `intervalo_medio_dias`, `atraso_relativo`, `pct_compras_fim_de_semana` | CSV, Excel |
| Agregações | `qtd_compras`, `total_gasto`, `ticket_medio`, `categorias_distintas`, `margem_pct`, `pct_compras_online`, `qtd_compras_90d`, `gasto_90d`, `tendencia_compras`, `compras_por_mes` | CSV, JSON |
| Encoding | `canal_*` (3 colunas), `regiao_*` (5 colunas) | CSV, API IBGE |
| Localidade | `capital`, `populacao_log`, `idhm`, `pib_per_capita` | Kaggle |

São 29 colunas. Como cada uma é calculada e por que ajuda:
[`reports/documentacao_features.csv`](reports/documentacao_features.csv).

## Modelo e métricas

Três classificadores e um baseline que sempre responde "não é churn". Todos em um `Pipeline` do scikit-learn
(imputação, padronização e classificador). Divisão 80/20 estratificada. O modelo é escolhido pelo F1 da validação
cruzada (5 dobras, só no treino); o teste (200 clientes) fica para a avaliação final.

| Modelo | F1 (CV) | Accuracy | Precision | Recall | F1 | ROC AUC |
|---|---|---|---|---|---|---|
| **Regressão Logística (escolhido)** | 0,601 | 0,785 | 0,656 | 0,645 | 0,650 | 0,790 |
| Random Forest | 0,599 | 0,785 | 0,721 | 0,500 | 0,590 | 0,789 |
| Gradient Boosting | 0,555 | 0,760 | 0,750 | 0,339 | 0,467 | 0,728 |
| Baseline | 0,000 | 0,690 | 0,000 | 0,000 | 0,000 | 0,500 |

A métrica principal é o **F1 da classe churn**. A accuracy engana com classes desbalanceadas: o baseline acerta 69%
sem encontrar nenhum churn.

As métricas ficam em [`reports/`](reports/) e na tabela `ml.metricas_modelo`.

## Análise dos resultados

- **O modelo encontra 40 dos 62 churns do teste** (recall 0,645) e acerta 40 dos 61 alertas (precision 0,656).
- **O ranking de risco funciona.** Na faixa de risco alto, 69% dos clientes saíram; na de risco baixo, 15%.
- **Recência e atividade recente dominam.** `dias_sem_comprar` e `qtd_compras_90d` são as features mais importantes.
- **Regressão Logística e Random Forest empataram** na validação cruzada. Ficou o modelo mais simples.
- **As fontes externas não melhoraram a previsão.** O F1 da validação cruzada vai de 0,596 para 0,601 com as
  features de localidade, menos que o desvio entre dobras (0,043). Elas serviram para a análise por região.

A análise completa, com gráficos, está no [notebook final](notebooks/02_projeto_integrador.ipynb) e no
[relatório em PDF](relatorio_projeto_integrador.pdf).

## Limitações

- Compras, clientes e catálogo são simulados, com premissas de abandono definidas em `src/gerar_dados.py`.
  Só o IBGE e o Kaggle são dados reais.
- O abandono simulado tem um componente aleatório grande, o que limita o teto de qualquer modelo.
- São 30 cidades com clientes, então os indicadores do Kaggle quase identificam a cidade.
- A avaliação usa uma única data de corte e a carga é sempre completa (não incremental).
