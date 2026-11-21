-- 03. Indicadores do Banco Central por ano.
-- IPCA: número-índice mensal acumulado. A receita de um ano é trazida a preços do último
-- mês da série usando o índice médio daquele ano (a receita se acumula ao longo do ano).
CREATE OR REPLACE TABLE ipca_indice AS
SELECT data,
       valor AS ipca_mes,
       exp(sum(ln(1 + valor / 100)) OVER (ORDER BY data)) AS indice
FROM bruto_ipca_mensal;

CREATE OR REPLACE TABLE macro AS
WITH ipca AS (
    SELECT year(data)                                   AS ano,
           avg(indice)                                  AS indice_medio,
           100 * (exp(sum(ln(1 + ipca_mes / 100))) - 1) AS ipca_ano
    FROM ipca_indice
    GROUP BY year(data)
),
selic AS (
    SELECT year(data) AS ano, avg(valor) AS selic_media
    FROM bruto_selic_anual
    GROUP BY year(data)
)
SELECT i.ano,
       i.ipca_ano,
       s.selic_media,
       (SELECT indice FROM ipca_indice ORDER BY data DESC LIMIT 1) / i.indice_medio AS fator_real
FROM ipca i
LEFT JOIN selic s USING (ano)
ORDER BY i.ano;
