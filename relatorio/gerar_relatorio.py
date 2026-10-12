"""Monta relatorio.html a partir dos arquivos gerados pelo pipeline, pelos notebooks e de evidencias/.

Nada é digitado à mão: números, tabelas e gráficos são lidos de reports/, evidencias/ e das saídas dos notebooks.

    python relatorio/gerar_relatorio.py
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --no-pdf-header-footer \
        --print-to-pdf=relatorio_projeto_integrador.pdf relatorio/relatorio.html
"""
import csv
import html
import json
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
REPO = 'https://github.com/Lorenalgm/projeto-integrador-engenharia-dados'


def linhas(caminho):
    return (RAIZ / caminho).read_text().splitlines()


def ler_csv(caminho):
    with open(RAIZ / caminho, newline='') as f:
        return list(csv.DictReader(f))


def trecho(caminho, ini, fim=None, n=None):
    """Linhas a partir da primeira que contém `ini`, até antes de `fim` ou por `n` linhas."""
    ls = linhas(caminho)
    i = next(k for k, l in enumerate(ls) if ini in l)
    if fim is not None:
        j = next(k for k in range(i + 1, len(ls)) if fim in ls[k])
    else:
        j = len(ls) if n is None else i + n
    return ls[i:j]


def pre(*partes, larga=False):
    out = []
    for p in partes:
        out += [p] if isinstance(p, str) else p
    while out and not out[-1].strip():
        out.pop()
    return ("<pre class='larga'>" if larga else "<pre>") + html.escape("\n".join(out)) + "</pre>"


def img(caminho, legenda, largura=100):
    return (f'<figure style="width:{largura}%"><img src="../{caminho}">'
            f'<figcaption>{legenda}</figcaption></figure>')


def shot(caminho, legenda, largura=100):
    """Print de tela. Se o arquivo ainda não existe, não entra no relatório."""
    if not (RAIZ / caminho).exists():
        print(f'aviso: print ausente, ficou fora do relatório: {caminho}')
        return ''
    return (f'<figure style="width:{largura}%"><div class="shot"><img src="../{caminho}"></div>'
            f'<figcaption>{legenda}</figcaption></figure>')


def tabela(cabecalho, registros, classes=''):
    th = ''.join(f'<th>{html.escape(c)}</th>' for c in cabecalho)
    trs = ''.join('<tr>' + ''.join(f'<td>{c}</td>' for c in r) + '</tr>' for r in registros)
    return f'<table class="{classes}"><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>'


def inteiro(v):
    return f'{int(float(v)):,}'.replace(',', '.')


def dec(v, casas=3):
    return f'{float(v):.{casas}f}'.replace('.', ',')


def saidas(notebook):
    """(código, texto impresso, markdown exibido, ordem de execução) de cada célula de código de um notebook executado."""
    nb = json.loads((RAIZ / notebook).read_text())
    out = []
    for cel in nb['cells']:
        if cel['cell_type'] != 'code':
            continue
        texto = markdown = ''
        for o in cel.get('outputs', []):
            dados = o.get('data', {})
            if o.get('output_type') == 'stream':
                texto += ''.join(o['text'])
            elif 'text/markdown' in dados:
                markdown += ''.join(dados['text/markdown'])
            elif 'text/plain' in dados and 'image/png' not in dados:
                texto += ''.join(dados['text/plain'])
        out.append((''.join(cel['source']), texto, markdown, cel.get('execution_count')))
    return out


def saida(celulas, marcador, markdown=False):
    """Saída da célula cujo código contém `marcador`."""
    cel = next(c for c in celulas if marcador in c[0])
    return cel[2].strip() if markdown else cel[1].rstrip().splitlines()


def md(texto):
    """Markdown simples (lista com negrito e código) para HTML."""
    itens = re.split(r'\n- ', '\n' + texto.strip())[1:]

    def fmt(t):
        t = html.escape(' '.join(t.split()), quote=False)
        t = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', t)
        return re.sub(r'`(.+?)`', r'<code>\1</code>', t)
    return '<ul>' + ''.join(f'<li>{fmt(i)}</li>' for i in itens) + '</ul>'


def entidade(nome, colunas, origem):
    campos = ''.join(f'<div class="{"pk" if "PK" in c else ""}">{c}</div>' for c in colunas)
    return f'<div class="ent"><div class="ent-nome">{nome}</div>{campos}<div class="ent-origem">{origem}</div></div>'


# ---------- dados ----------
nb_eda, nb_final = saidas('notebooks/01_analise_exploratoria.ipynb'), saidas('notebooks/02_projeto_integrador.ipynb')
for nome, nb in [('EDA', nb_eda), ('final', nb_final)]:
    assert [c[3] for c in nb] == list(range(1, len(nb) + 1)), f'notebook {nome} não foi executado em ordem do início ao fim'

PG = 'evidencias/03_postgres.txt'
etapas = ler_csv('reports/etapas_etl.csv')
doc = ler_csv('reports/documentacao_features.csv')
modelos = ler_csv('reports/comparacao_modelos.csv')
fontes_ext = ler_csv('reports/comparacao_fontes.csv')
metricas = json.loads((RAIZ / 'reports/metricas.json').read_text())
escolhido = next(m for m in modelos if m['escolhido'] == 'True')
compras = [e for e in etapas if e['fonte'] == 'compras']
n_bruto, n_limpo = int(compras[0]['entraram']), int(compras[-1]['restaram'])
versoes = saida(nb_final, 'print(f\'Python')[0]

tab_etapas = tabela(['Fonte', 'Etapa', 'Entraram', 'Removidos', 'Restaram', 'O que foi feito'],
                    [(e['fonte'], e['etapa'], inteiro(e['entraram']), inteiro(e['removidos']), inteiro(e['restaram']),
                      html.escape(e['descricao'])) for e in etapas], 'num etapas')
tab_doc = tabela(['Feature', 'Grupo', 'Fonte', 'Como é calculada', 'O que representa e por que ajuda'],
                 [(f"<code>{html.escape(d['feature'])}</code>", d['grupo'], d['fonte'], html.escape(d['como é calculada']),
                   html.escape(d['o que representa e por que ajuda'])) for d in doc], 'doc')
tab_modelos = tabela(
    ['Modelo', 'F1 (CV)', 'Desvio (CV)', 'ROC AUC (CV)', 'Accuracy', 'Precision', 'Recall', 'F1', 'ROC AUC'],
    [((f"<b>{m['modelo']}</b>" if m is escolhido else m['modelo']),
      *(dec(m[c]) for c in ['cv_f1', 'cv_f1_desvio', 'cv_roc_auc', 'accuracy', 'precision', 'recall', 'f1', 'roc_auc']))
     for m in modelos], 'num')
tab_fontes_ext = tabela(['Features usadas', 'Quantidade', 'F1 (CV)', 'Desvio (CV)', 'ROC AUC (CV)'],
                        [(f['features usadas'], f['quantidade'], dec(f['cv_f1']), dec(f['cv_f1_desvio']), dec(f['cv_roc_auc']))
                         for f in fontes_ext], 'num')
cortes = [l.split()[1:] for l in saida(nb_final, 'cortes = pd.DataFrame')[1:]]
tab_cortes = tabela(['Corte', 'Accuracy', 'Precision', 'Recall', 'F1', 'Acionados'],
                    [(dec(c[0], 1), *(dec(v) for v in c[1:5]), c[5]) for c in cortes], 'num mini')
tab_fontes = tabela(['#', 'Fonte', 'Formato', 'Conteúdo', 'Origem'], [
    (1, 'Sistema de vendas', 'CSV', 'uma linha por compra', 'fictícia, semente fixa'),
    (2, 'CRM', 'Excel', 'cadastro de clientes', 'fictícia, semente fixa'),
    (3, 'Catálogo', 'JSON aninhado', 'produtos por categoria, com preço e custo', 'fictícia, semente fixa'),
    (4, 'API de Localidades do IBGE', 'API REST', 'município, UF e região', 'dado real, consultado a cada execução'),
    (5, 'Kaggle <code>crisparada/brazilian-cities</code>', 'CSV via API do Kaggle', 'população, IDHM e PIB per capita',
     'dado real, CC BY-SA 4.0'),
], 'curta')

diagrama = f"""<div class="der">
<div class="der-col">{entidade('dw.dim_localidade', ['codigo_ibge PK', 'municipio, uf, estado', 'regiao', 'capital, populacao', 'idhm, pib_per_capita'], 'API IBGE + Kaggle')}
<div class="seta">1 : N por codigo_ibge</div>
{entidade('dw.dim_cliente', ['cliente_id PK', 'nome, email', 'data_nascimento', 'segmento', 'data_cadastro', 'codigo_ibge FK'], 'Excel')}</div>
<div class="seta lado-seta">1 : N<br>cliente_id</div>
<div class="der-col">{entidade('dw.fato_compras', ['id_compra PK', 'cliente_id FK', 'produto_id FK', 'data_compra FK', 'quantidade', 'valor', 'custo_total', 'canal, pagamento'], 'CSV + custo do JSON')}</div>
<div class="seta lado-seta">N : 1<br>produto_id<br><br>N : 1<br>data_compra</div>
<div class="der-col">{entidade('dw.dim_produto', ['produto_id PK', 'nome, categoria', 'preco, custo'], 'JSON')}
{entidade('dw.dim_data', ['data PK', 'ano, trimestre, mes', 'nome_mes', 'dia_semana, nome_dia', 'fim_de_semana'], 'gerada pelo ETL')}</div>
</div>"""

checklist = tabela(['Item do checklist', 'Onde está'], [
    ('Pelo menos 2 fontes de dados', 'Cinco fontes: <code>data/raw/</code>, <code>src/extract.py</code> (seção 1)'),
    ('Dados armazenados e modelados no PostgreSQL', '<code>sql/schema.sql</code>, schemas <code>staging</code>, <code>dw</code> e <code>ml</code> (seção 2)'),
    ('Processo ETL em Python', '<code>src/extract.py</code>, <code>src/transform.py</code>, <code>src/load.py</code>, <code>src/pipeline.py</code> (seção 3)'),
    ('Features preparadas e documentadas', '<code>src/features.py</code>, <code>reports/documentacao_features.csv</code> (seção 5)'),
    ('Modelo de classificação treinado', '<code>src/model.py</code>, <code>models/modelo_churn.pkl</code> (seção 6)'),
    ('Métricas do modelo apresentadas', '<code>reports/metricas.json</code>, <code>reports/comparacao_modelos.csv</code>, tabela <code>ml.metricas_modelo</code> (seções 6 e 7)'),
    ('Notebook de análise exploratória', '<code>notebooks/01_analise_exploratoria.ipynb</code> (seção 4)'),
    ('README com instruções claras', '<code>README.md</code>'),
    ('Repositório Git acessível', f'{REPO} (público, seção 8)'),
    ('Notebook final (.ipynb)', '<code>notebooks/02_projeto_integrador.ipynb</code>'),
], 'curta')

corpo = f"""
<h1>Projeto Integrador: pipeline de dados para previsão de churn</h1>
<p>Disciplina de Engenharia de Dados.<br>
Repositório: <b>{REPO}</b></p>
<p><b>Problema.</b> Uma loja de artigos esportivos quer saber quais clientes vão parar de comprar, para agir antes.
É um problema de <b>classificação</b>: para cada cliente ativo, prever se ele dará churn nos próximos 90 dias.
A solução é um pipeline de ponta a ponta, executado com um único comando (<code>python -m src.pipeline</code>).</p>
<div class="fluxo"><span>Fontes de dados<small>CSV, Excel, JSON,<br>API IBGE, Kaggle</small></span><i>→</i>
<span>PostgreSQL<small>staging, dw (estrela), ml</small></span><i>→</i><span>ETL Python<small>extract, transform, load</small></span><i>→</i>
<span>Features<small>{fontes_ext[-1]['quantidade']} por cliente</small></span><i>→</i><span>Machine Learning<small>3 modelos + baseline</small></span><i>→</i>
<span>Métricas<small>F1, recall, ROC AUC</small></span><i>→</i><span>Resultados<small>modelo .pkl e tabelas em ml</small></span></div>
<p>Resultado no conjunto de teste ({metricas['clientes_no_teste']} clientes): <b>{metricas['modelo']}</b> com F1 {dec(metricas['f1'])},
recall {dec(metricas['recall'])}, precision {dec(metricas['precision'])}, ROC AUC {dec(metricas['roc_auc'])} e accuracy
{dec(metricas['accuracy'])}. Ambiente: {versoes}, PostgreSQL 14. Os números, tabelas e gráficos deste documento são lidos
dos arquivos gravados pelo pipeline e pelos notebooks.</p>

<h2>1. Coleta de dados de 2 ou mais fontes</h2>
<p>São cinco fontes em quatro formatos. As três primeiras simulam os sistemas internos da loja e chegam sujas de propósito;
as duas últimas são dados públicos reais e enriquecem o cadastro, que só tem o nome da cidade.</p>
{tab_fontes}
<p><code>src/extract.py</code> lê tudo como texto, sem tratar nada. A API do IBGE tem três tentativas e a resposta fica guardada
em disco para o caso de a API não responder. O arquivo do Kaggle é baixado pela API do Kaggle quando não existe e fica
versionado no repositório, então não é preciso ter conta para reproduzir.</p>
<p>As fontes fictícias são geradas por <code>src/gerar_dados.py</code> (semente fixa), que simula o ritmo de compra e a data de
abandono de cada cliente e depois injeta a sujeira abaixo.</p>
{pre(linhas('evidencias/01_gerar_dados.txt'))}

<h2>2. Armazenamento e modelagem no PostgreSQL</h2>
<p><code>sql/schema.sql</code> cria três schemas no banco <code>projeto_integrador</code>:</p>
<ul>
<li><b><code>staging</code></b>: cada fonte como chegou, tudo em texto. Dá rastreabilidade ao que a limpeza rejeitou.</li>
<li><b><code>dw</code></b>: modelo estrela com os dados limpos e integrados. Chaves primárias e estrangeiras, <code>CHECK</code>
nas regras de negócio, índices nas chaves do fato, a tabela <code>etl_etapas</code> (trilha da limpeza) e a visão
<code>vw_compras</code>, que junta o fato com as dimensões.</li>
<li><b><code>ml</code></b>: <code>features_cliente</code>, <code>metricas_modelo</code> e <code>previsoes_teste</code>.</li>
</ul>
{diagrama}
<p class="nota">Modelo estrela do schema <code>dw</code>. A dimensão de localidade liga ao cliente (floco de neve em um nível)
porque a cidade é um atributo do cliente, não da compra.</p>
<div class="lado">
<div style="width:53%">{shot('evidencias/prints/print_psql_verificacao.png', 'Terminal: psql executando sql/verificacao.sql.')}</div>
<div style="width:45%"><p><code>sql/verificacao.sql</code> confere a carga direto no banco:</p>
<ul>
<li><b>Consultas 1 a 3:</b> linhas por tabela, qualidade do fato (tudo zero) e a trilha do ETL.</li>
<li><b>Consulta 4:</b> chaves estrangeiras lidas do catálogo do PostgreSQL.</li>
<li><b>Consulta 5:</b> receita, margem e IDHM por região. Só é possível com as fontes integradas: compra do CSV, custo
do JSON, cliente do Excel, região da API do IBGE e IDHM do Kaggle.</li>
<li><b>Consultas 7 e 8:</b> métricas dos modelos e taxa real de churn por faixa de risco, gravadas pelo pipeline.</li>
</ul>
<p>Estrutura da tabela fato, com índices, <code>CHECK</code> e chaves estrangeiras:</p>
{pre(trecho(PG, "$ psql -d projeto_integrador -c '\\d dw.fato_compras'", fim='$ psql -d projeto_integrador -f'), larga=True)}</div>
</div>

<h2>3. Processo de ETL em Python</h2>
<p>O ETL está em três módulos, orquestrados por <code>src/pipeline.py</code>: <code>extract.py</code> (leitura das fontes),
<code>transform.py</code> (limpeza e integração, em funções puras de pandas) e <code>load.py</code> (criação do banco, carga e
verificação). Cada etapa de limpeza registra quantas linhas entraram, quantas removeu e quantas restaram; a mesma tabela é
gravada em <code>dw.etl_etapas</code>.</p>
{tab_etapas}
<p>Das {inteiro(n_bruto)} linhas de compras, {inteiro(n_limpo)} ({dec(100 * n_limpo / n_bruto, 1)}%) chegaram ao modelo estrela.
Decisões técnicas:</p>
<ul>
<li><b>Outliers pelo catálogo, não por estatística.</b> O preço unitário pago é comparado com o preço de tabela do próprio
produto (aceito de 50% a 110%). A loja vende de protetor bucal (R$ 24,90) a estação de musculação (R$ 3.499,00); um limite
único para a coluna <code>valor</code> trataria produto caro como erro.</li>
<li><b>Integridade referencial.</b> Compra de cliente fora do cadastro ou de produto fora do catálogo é removida antes da
carga, porque a chave estrangeira do banco não aceitaria.</li>
<li><b>Essenciais são removidos, não preenchidos.</b> Compra sem cliente, data ou valor não entra.</li>
<li><b>Não essenciais ficam nulos no banco.</b> Nascimento inválido e cidade ausente não são inventados no ETL. A imputação
fica no Pipeline do modelo, que calcula a mediana só com o treino.</li>
<li><b>Integração por nome + UF.</b> Cidade e UF do cliente viram o código do município do IBGE. O Kaggle não traz esse
código, então a junção usa nome sem acento + UF (existe Santana no Amapá e na Bahia).</li>
<li><b>Carga em transação.</b> As tabelas do <code>dw</code> entram em uma única transação. No fim, o pipeline confere no
próprio banco contagens, receita e junções.</li>
</ul>
{img('reports/figuras/02_outliers_preco.png', 'Preço unitário pago em relação ao preço de tabela, antes e depois da limpeza. Antes, há compras com 10 e 100 vezes o preço do produto; depois, tudo fica entre 85% e 100% (descontos de até 15%).', 92)}
<p>Execução completa, da extração às métricas do modelo:</p>
{shot('evidencias/prints/print_terminal_pipeline.png', 'Terminal: python -m src.pipeline. Cada linha mostra a etapa, a fonte ou tabela e a contagem de linhas.', 92)}
<p>As regras de limpeza têm testes automatizados (<code>tests/test_transform.py</code>), que rodam sem banco e sem rede:</p>
{pre([l for l in linhas('evidencias/04_testes.txt') if l.startswith(('$', 'tests/', '===')) and 'session starts' not in l], larga=True)}

<h2>4. Análise exploratória (notebook)</h2>
<p><code>notebooks/01_analise_exploratoria.ipynb</code> lê tudo do PostgreSQL e cobre qualidade do dado bruto, vendas, produtos,
clientes, localidade, churn por grupo e correlação das features com o target.</p>
{img('reports/figuras/01_ausentes.png', 'Valores ausentes nas duas fontes principais, lidos de staging.', 86)}
{img('reports/figuras/03_evolucao_mensal.png', 'Compras, receita e clientes ativos por mês, agregados no banco com a dimensão de data. A linha tracejada é a data de corte do modelo.', 70)}
{img('reports/figuras/04_categorias.png', 'Receita, volume e margem por categoria. A margem só existe porque o catálogo (JSON) traz o custo de cada produto.')}
{img('reports/figuras/06_localidade.png', 'Clientes por região e por cidade (API do IBGE) e perfil das cidades atendidas (IDHM e PIB per capita do Kaggle).')}
{img('reports/figuras/07_churn_por_grupo.png', 'Taxa de churn por grupo. Recência e atividade recente separam muito mais do que segmento, canal ou região.')}
<p><b>Achados</b> (última célula do notebook):</p>
{md(saida(nb_eda, 'Markdown(f"""', markdown=True))}

<h2>5. Preparação dos dados e criação de features</h2>
<p><code>src/features.py</code> lê a visão <code>dw.vw_compras</code> do PostgreSQL e monta uma linha por cliente, gravada em
<code>ml.features_cliente</code>.</p>
<ul>
<li><b>Target.</b> <code>churn = 1</code> se o cliente não comprou nos 90 dias depois da data de corte (31/03/2026).</li>
<li><b>Sem vazamento.</b> As features usam somente as compras até o corte. Se o churn fosse definido como "mais de 90 dias
sem comprar" e essa mesma coluna entrasse como feature, o modelo acertaria tudo sem prever nada.</li>
<li><b>Base.</b> Clientes ativos, com pelo menos uma compra nos 180 dias antes do corte.</li>
<li><b>Nulos e escala.</b> Imputação pela mediana e padronização ficam dentro do Pipeline do modelo, ajustadas só no treino.</li>
</ul>
{pre(saida(nb_final, 'features.preparar(engine)')[:3])}
{tab_doc}
{img('reports/figuras/08_correlacao_target.png', 'Correlação de Pearson de cada feature com o churn. Lista completa, com Spearman, em reports/correlacao_target.csv.', 66)}

<h2>6. Modelo de classificação</h2>
<p><code>src/model.py</code> treina três modelos de famílias diferentes e um baseline que sempre responde "não é churn". Todos
ficam em um <code>Pipeline</code> do scikit-learn (imputação, padronização e classificador). Regressão Logística e Random
Forest usam <code>class_weight='balanced'</code> para compensar o desbalanceamento. Divisão 80/20 estratificada. As colunas
CV são a média da validação cruzada (5 dobras estratificadas, só no treino); as demais são do teste.</p>
{tab_modelos}
<p><b>Modelo escolhido: {escolhido['modelo']}.</b> Critério: maior F1 médio na validação cruzada. A escolha não usa o teste,
que fica só para a avaliação final.</p>

<h2>7. Avaliação, métricas e resultados</h2>
<p>A métrica principal é o <b>F1 da classe churn</b>, porque a accuracy engana com classes desbalanceadas: o baseline acerta
{dec(next(m for m in modelos if m['modelo'].startswith('Baseline'))['accuracy'])} sem encontrar nenhum churn. Recall mede
quantos churns o modelo encontra, precision mede quantos alertas estão certos e ROC AUC mede a qualidade do ranking de risco.</p>
{img('reports/figuras/10_roc_e_matrizes.png', 'Curva ROC e matrizes de confusão no teste.')}
<div class="lado">
<div style="width:56%">{img('reports/figuras/11_importancia_features.png', 'Importância por permutação do modelo escolhido.')}</div>
<div style="width:42%"><p><b>Faixas de risco.</b> Clientes do teste agrupados pela probabilidade prevista. A taxa real de churn
sobe de uma faixa para a outra, sinal de que o modelo ordena bem.</p>
{pre(trecho(PG, '8. Taxa real de churn', n=8)[1:])}
<p><b>Ponto de corte.</b> Baixar o corte encontra mais churns ao custo de mais alarmes falsos.</p>
{tab_cortes}</div>
</div>
<p><b>O que as fontes externas acrescentam.</b> O modelo escolhido foi treinado de novo sem as features de localidade
e comparado na validação cruzada:</p>
{tab_fontes_ext}
<p>As métricas também ficam no PostgreSQL (<code>ml.metricas_modelo</code>) e as previsões do teste em
<code>ml.previsoes_teste</code>.</p>
<p><b>Conclusões</b> (última célula do notebook final):</p>
{md(saida(nb_final, 'Markdown(f"""', markdown=True))}

<h2>8. Repositório, documentação e uso do Git</h2>
<p>O repositório é público, com commits atômicos escritos em português no padrão Conventional Commits
(<code>feat</code>, <code>fix</code>, <code>test</code>, <code>docs</code>, <code>chore</code>). O <code>README.md</code> traz descrição,
organização, diagrama do banco, instruções de execução (PostgreSQL local ou Docker) e resultados.</p>
<div class="lado">
<div style="width:49%">{shot('evidencias/prints/github_repositorio.png', 'Repositório no GitHub.')}</div>
<div style="width:49%">{shot('evidencias/prints/github_commits.png', 'Commits mais recentes.')}</div>
</div>
{shot('evidencias/prints/print_jupyter_notebook_final.png', 'JupyterLab com o notebook final executado.', 60)}

<h2>Checklist da entrega</h2>
{checklist}
"""

pagina = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<title>Projeto Integrador: pipeline de dados para previsão de churn</title><style>
@page {{ size: A4; margin: 13mm 14mm; }}
body {{ font: 9.6pt/1.42 -apple-system, "Helvetica Neue", Arial, sans-serif; color: #1a1a1a; margin: 0; }}
h1 {{ font-size: 16pt; margin: 0 0 4pt; }}
h2 {{ font-size: 12.5pt; margin: 16pt 0 4pt; padding-bottom: 2pt; border-bottom: 1.2pt solid #1a1a1a; break-after: avoid; }}
p {{ margin: 3pt 0 4pt; }}
ul {{ margin: 3pt 0 5pt; padding-left: 14pt; }}
li {{ margin-bottom: 2pt; }}
.nota {{ color: #555; font-size: 8.4pt; }}
code {{ font: 8.2pt Menlo, Consolas, monospace; background: #f1f1f1; padding: 0 2pt; border-radius: 2pt; }}
pre {{ font: 6.6pt/1.32 Menlo, Consolas, monospace; background: #f6f6f6; border: 0.6pt solid #d4d4d4;
      border-radius: 3pt; padding: 5pt 6pt; margin: 4pt 0 6pt; white-space: pre-wrap; overflow-wrap: anywhere; }}
pre.larga {{ font-size: 5.6pt; }}
table {{ border-collapse: collapse; margin: 4pt 0 7pt; font-size: 8.4pt; width: 100%; }}
th {{ text-align: left; border-bottom: 1pt solid #1a1a1a; padding: 2pt 5pt; font-size: 8pt; }}
td {{ border-bottom: 0.5pt solid #d9d9d9; padding: 2pt 5pt; vertical-align: top; }}
tr {{ break-inside: avoid; }}
table.num, table.curta {{ break-inside: avoid; }}
table.num td:not(:first-child), table.num th:not(:first-child) {{ text-align: right; font-variant-numeric: tabular-nums; }}
table.etapas td:nth-child(2), table.etapas th:nth-child(2) {{ text-align: left; }}
table.etapas td:last-child, table.etapas th:last-child {{ text-align: left; width: 46%; }}
table.doc {{ font-size: 7.6pt; }}
table.mini {{ font-size: 7.2pt; }}
table.mini th {{ font-size: 6.8pt; padding: 2pt 3pt; }}
table.mini td {{ padding: 2pt 3pt; }}
table.doc code {{ font-size: 7pt; }}
figure {{ margin: 6pt auto 8pt; break-inside: avoid; }}
figure img {{ width: 100%; display: block; }}
.shot {{ border: 0.6pt solid #bbb; }}
figcaption {{ font-size: 8pt; color: #555; margin-top: 2pt; }}
.lado {{ display: flex; gap: 2%; align-items: flex-start; break-inside: avoid; }}
.lado figure {{ margin-top: 2pt; }}
.fluxo {{ display: flex; align-items: stretch; gap: 3pt; margin: 6pt 0 8pt; break-inside: avoid; }}
.fluxo span {{ flex: 1; border: 0.8pt solid #2a78d6; border-radius: 3pt; padding: 4pt 3pt; text-align: center; font-weight: 600; font-size: 8pt; }}
.fluxo small {{ display: block; font-weight: 400; font-size: 6.8pt; color: #555; margin-top: 2pt; }}
.fluxo i {{ align-self: center; font-style: normal; color: #2a78d6; }}
.der {{ display: flex; align-items: center; justify-content: center; gap: 6pt; margin: 8pt 0 4pt; break-inside: avoid; }}
.der-col {{ display: flex; flex-direction: column; gap: 5pt; width: 27%; }}
.ent {{ border: 0.8pt solid #1a1a1a; border-radius: 3pt; font: 7.4pt Menlo, Consolas, monospace; }}
.ent div {{ padding: 1pt 5pt; }}
.ent-nome {{ background: #2a78d6; color: white; font-weight: 700; padding: 2.5pt 5pt !important; }}
.ent .pk {{ font-weight: 700; border-bottom: 0.5pt solid #d4d4d4; }}
.ent-origem {{ background: #f1f1f1; color: #555; font-family: -apple-system, Arial, sans-serif; font-size: 7pt; border-top: 0.5pt solid #d4d4d4; }}
.seta {{ font-size: 7pt; color: #555; text-align: center; }}
.lado-seta {{ width: 9%; }}
</style></head><body>{corpo}</body></html>"""

destino = Path(__file__).parent / 'relatorio.html'
destino.write_text(pagina)
assert '—' not in pagina and '–' not in pagina, 'travessão encontrado'
print(f'ok: {destino}')
