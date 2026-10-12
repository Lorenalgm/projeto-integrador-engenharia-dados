-- Verificação da carga e consultas analíticas no banco projeto_integrador.
--   psql -d projeto_integrador -f sql/verificacao.sql

\echo '1. Linhas por tabela (staging = bruto, dw = limpo, ml = modelo)'
SELECT 'staging.compras' AS tabela, count(*) AS linhas FROM staging.compras
UNION ALL SELECT 'staging.clientes', count(*) FROM staging.clientes
UNION ALL SELECT 'staging.produtos', count(*) FROM staging.produtos
UNION ALL SELECT 'staging.municipios_ibge', count(*) FROM staging.municipios_ibge
UNION ALL SELECT 'staging.cidades_kaggle', count(*) FROM staging.cidades_kaggle
UNION ALL SELECT 'dw.fato_compras', count(*) FROM dw.fato_compras
UNION ALL SELECT 'dw.dim_cliente', count(*) FROM dw.dim_cliente
UNION ALL SELECT 'dw.dim_produto', count(*) FROM dw.dim_produto
UNION ALL SELECT 'dw.dim_localidade', count(*) FROM dw.dim_localidade
UNION ALL SELECT 'dw.dim_data', count(*) FROM dw.dim_data
UNION ALL SELECT 'ml.features_cliente', count(*) FROM ml.features_cliente
UNION ALL SELECT 'ml.previsoes_teste', count(*) FROM ml.previsoes_teste;

\echo '2. Qualidade do fato: tudo deve ser zero'
SELECT count(*) - count(DISTINCT id_compra) AS ids_repetidos,
       count(*) FILTER (WHERE valor <= 0 OR quantidade NOT BETWEEN 1 AND 20) AS valores_invalidos,
       count(*) FILTER (WHERE data_compra > DATE '2026-06-30') AS datas_futuras,
       count(*) FILTER (WHERE c.cliente_id IS NULL) AS sem_cliente,
       count(*) FILTER (WHERE p.produto_id IS NULL) AS sem_produto,
       count(*) FILTER (WHERE f.valor / f.quantidade NOT BETWEEN 0.5 * p.preco AND 1.1 * p.preco) AS preco_fora_da_faixa
FROM dw.fato_compras f
LEFT JOIN dw.dim_cliente c USING (cliente_id)
LEFT JOIN dw.dim_produto p USING (produto_id);

\echo '3. Trilha do ETL: linhas que entraram, foram removidas e restaram em cada etapa'
SELECT fonte, etapa, entraram, removidos, restaram FROM dw.etl_etapas ORDER BY ordem;

\echo '4. Chaves estrangeiras do modelo estrela'
SELECT conrelid::regclass AS tabela, pg_get_constraintdef(oid) AS definicao
FROM pg_constraint
WHERE contype = 'f' AND connamespace = 'dw'::regnamespace
ORDER BY 1, 2;

\echo '5. Receita, margem e IDHM por região (junta as cinco fontes)'
SELECT coalesce(regiao, 'Sem cidade') AS regiao, count(DISTINCT cliente_id) AS clientes, count(*) AS compras,
       round(sum(valor), 2) AS receita, round(100 * sum(margem) / sum(valor), 1) AS margem_pct,
       round(avg(idhm), 3) AS idhm_medio
FROM dw.vw_compras
GROUP BY 1 ORDER BY receita DESC;

\echo '6. Receita por categoria'
SELECT categoria, count(*) AS compras, round(sum(valor), 2) AS receita, round(avg(valor), 2) AS ticket_medio
FROM dw.vw_compras
GROUP BY 1 ORDER BY receita DESC;

\echo '7. Métricas dos modelos gravadas pelo pipeline'
SELECT modelo, escolhido, cv_f1, accuracy, precision, recall, f1, roc_auc
FROM ml.metricas_modelo ORDER BY cv_f1 DESC;

\echo '8. Taxa real de churn por faixa de risco prevista (conjunto de teste)'
SELECT risco, count(*) AS clientes, sum(churn_real) AS deram_churn, round(100.0 * avg(churn_real), 1) AS taxa_real_pct
FROM ml.previsoes_teste
GROUP BY risco ORDER BY taxa_real_pct;
