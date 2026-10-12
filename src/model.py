"""Modelo: treina, compara e avalia classificadores de churn e guarda o melhor.

Todos os modelos ficam dentro de um Pipeline do scikit-learn (imputação pela mediana + padronização +
classificador), ajustado só com o treino. A escolha usa a validação cruzada; o teste fica para a avaliação final.
"""
import json
import logging

import joblib
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_validate, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src import config

log = logging.getLogger('pipeline')

BASELINE = 'Baseline (classe majoritária)'
CAMINHO_MODELO = config.MODELOS / 'modelo_churn.pkl'
METRICAS = ['accuracy', 'precision', 'recall', 'f1', 'roc_auc']


def montar(classificador):
    return Pipeline([('imputer', SimpleImputer(strategy='median')), ('scaler', StandardScaler()), ('modelo', classificador)])


def candidatos():
    return {
        BASELINE: montar(DummyClassifier(strategy='most_frequent')),
        'Regressão Logística': montar(LogisticRegression(max_iter=1000, class_weight='balanced')),
        'Random Forest': montar(RandomForestClassifier(n_estimators=300, min_samples_leaf=5, class_weight='balanced',
                                                       random_state=config.SEED)),
        'Gradient Boosting': montar(GradientBoostingClassifier(n_estimators=100, random_state=config.SEED)),
    }


def dividir(X, y):
    """80% treino e 20% teste, mantendo a mesma taxa de churn nos dois."""
    return train_test_split(X, y, test_size=0.2, random_state=config.SEED, stratify=y)


def validacao_cruzada(modelo, X, y):
    """Média e desvio do F1 e média do ROC AUC em 5 dobras estratificadas."""
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=config.SEED)
    notas = cross_validate(modelo, X, y, cv=cv, scoring=['f1', 'roc_auc'])
    return {'cv_f1': notas['test_f1'].mean(), 'cv_f1_desvio': notas['test_f1'].std(), 'cv_roc_auc': notas['test_roc_auc'].mean()}


def avaliar(y_real, y_previsto, y_prob):
    return {
        'accuracy': accuracy_score(y_real, y_previsto),
        'precision': precision_score(y_real, y_previsto, zero_division=0),
        'recall': recall_score(y_real, y_previsto),
        'f1': f1_score(y_real, y_previsto),
        'roc_auc': roc_auc_score(y_real, y_prob),
    }


def treinar_e_comparar(X_train, y_train, X_test, y_test):
    """Devolve (tabela de métricas ordenada pelo F1 da validação cruzada, modelos treinados, previsões no teste)."""
    modelos, linhas, previsoes = candidatos(), [], {}
    for nome, modelo in modelos.items():
        cv = validacao_cruzada(modelo, X_train, y_train)
        modelo.fit(X_train, y_train)
        previsoes[nome] = (modelo.predict(X_test), modelo.predict_proba(X_test)[:, 1])
        linhas.append({'modelo': nome, **cv, **avaliar(y_test, *previsoes[nome])})
        log.info('modelo    | %-30s | F1 (CV) %.3f | F1 teste %.3f | ROC AUC teste %.3f',
                 nome, linhas[-1]['cv_f1'], linhas[-1]['f1'], linhas[-1]['roc_auc'])
    comparacao = pd.DataFrame(linhas).sort_values('cv_f1', ascending=False).reset_index(drop=True)
    comparacao.insert(1, 'escolhido', comparacao['modelo'] == escolher(comparacao))
    return comparacao, modelos, previsoes


def escolher(comparacao):
    """Nome do modelo com o maior F1 médio na validação cruzada (o teste não entra na escolha)."""
    return comparacao[comparacao['modelo'] != BASELINE].sort_values('cv_f1', ascending=False).iloc[0]['modelo']


def importancia(modelo, X_test, y_test):
    """Importância por permutação: quanto o ROC AUC cai no teste ao embaralhar cada feature."""
    perm = permutation_importance(modelo, X_test, y_test, scoring='roc_auc', n_repeats=30, random_state=config.SEED)
    imp = pd.DataFrame({'importancia': perm.importances_mean, 'desvio': perm.importances_std}, index=X_test.columns)
    return imp.sort_values('importancia', ascending=False).rename_axis('feature')


def faixa_de_risco(prob):
    return pd.cut(prob, [0, 0.4, 0.7, 1], labels=['baixo', 'médio', 'alto'], include_lowest=True)


def salvar(engine, comparacao, modelos, previsoes, imp, X_test, y_test):
    """Grava o modelo em .pkl, as métricas em arquivo e no PostgreSQL e as previsões do teste no PostgreSQL."""
    nome = escolher(comparacao)
    config.MODELOS.mkdir(exist_ok=True)
    config.RESULTADOS.mkdir(exist_ok=True)
    joblib.dump(modelos[nome], CAMINHO_MODELO)

    comparacao.to_csv(config.RESULTADOS / 'comparacao_modelos.csv', index=False)
    imp.round(4).to_csv(config.RESULTADOS / 'importancia_features.csv')
    vencedor = comparacao[comparacao['modelo'] == nome].iloc[0]
    resumo = {'modelo': nome, 'data_de_corte': str(config.CORTE.date()), 'clientes_no_teste': len(y_test),
              'taxa_de_churn_no_teste': round(float(y_test.mean()), 4),
              **{m: round(float(vencedor[m]), 4) for m in ['cv_f1', 'cv_roc_auc', *METRICAS]}}
    (config.RESULTADOS / 'metricas.json').write_text(json.dumps(resumo, ensure_ascii=False, indent=2) + '\n')

    previsto, prob = previsoes[nome]
    tabela = pd.DataFrame({'cliente_id': X_test.index, 'churn_real': y_test.values, 'churn_previsto': previsto,
                           'prob_churn': prob.round(4), 'risco': faixa_de_risco(prob).astype(str)})
    with engine.begin() as con:
        con.exec_driver_sql('DELETE FROM ml.metricas_modelo')
        comparacao.round(4).to_sql('metricas_modelo', con, schema='ml', if_exists='append', index=False)
        tabela.to_sql('previsoes_teste', con, schema='ml', if_exists='replace', index=False)
    log.info('modelo    | escolhido: %s | salvo em %s (%d KB)', nome, CAMINHO_MODELO.relative_to(config.RAIZ),
             CAMINHO_MODELO.stat().st_size / 1024)
    return resumo
