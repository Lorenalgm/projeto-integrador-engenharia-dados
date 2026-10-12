"""Pipeline de ponta a ponta: fontes -> PostgreSQL -> ETL -> features -> modelo -> métricas.

    python -m src.pipeline                  # roda tudo
    python -m src.pipeline --gerar-dados    # antes, recria as fontes fictícias (o resultado é sempre o mesmo)
    python -m src.pipeline --so-etl         # para depois da carga no PostgreSQL
"""
import argparse
import logging
import time

from src import config, extract, features, gerar_dados, load, model, transform

log = logging.getLogger('pipeline')


def configurar_log():
    config.LOGS.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO, format='%(asctime)s | %(levelname)-7s | %(message)s', datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[logging.StreamHandler(), logging.FileHandler(config.LOGS / 'pipeline.log', mode='w')], force=True)


def etl():
    """Extract, Transform, Load e verificação. Devolve a engine do banco carregado."""
    fontes = extract.extrair()
    tabelas, etapas = transform.transformar(fontes)
    engine = load.conectar()
    load.criar_estrutura(engine)
    load.carregar_staging(engine, fontes)
    load.carregar_dw(engine, tabelas, etapas)
    load.verificar(engine, tabelas)
    config.RESULTADOS.mkdir(exist_ok=True)
    etapas.to_csv(config.RESULTADOS / 'etapas_etl.csv', index=False)
    return engine


def machine_learning(engine):
    """Features a partir do PostgreSQL, treino, comparação e gravação do melhor modelo."""
    X, y, _ = features.preparar(engine)
    features.documentacao().to_csv(config.RESULTADOS / 'documentacao_features.csv', index=False)
    X_train, X_test, y_train, y_test = model.dividir(X, y)
    comparacao, modelos, previsoes = model.treinar_e_comparar(X_train, y_train, X_test, y_test)
    imp = model.importancia(modelos[model.escolher(comparacao)], X_test, y_test)
    return model.salvar(engine, comparacao, modelos, previsoes, imp, X_test, y_test)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--gerar-dados', action='store_true', help='recria as fontes fictícias antes de rodar')
    parser.add_argument('--so-etl', action='store_true', help='não treina o modelo')
    args = parser.parse_args()

    configurar_log()
    inicio = time.perf_counter()
    log.info('=== início do pipeline | banco: %s ===', load.make_url(config.DATABASE_URL).render_as_string(hide_password=True))
    if args.gerar_dados:
        gerar_dados.main()
    engine = etl()
    if not args.so_etl:
        resumo = machine_learning(engine)
        log.info('resultado | %s | F1 %.3f | recall %.3f | precision %.3f | ROC AUC %.3f | accuracy %.3f',
                 resumo['modelo'], resumo['f1'], resumo['recall'], resumo['precision'], resumo['roc_auc'], resumo['accuracy'])
    log.info('=== fim do pipeline em %.1f s ===', time.perf_counter() - inicio)


if __name__ == '__main__':
    main()
