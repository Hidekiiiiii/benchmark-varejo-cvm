-- 05. Visão por segmento.
-- * Medianas, que resistem melhor a extremos do que a média.
-- * Crescimento real: receita a preços constantes (IPCA), sempre da MESMA empresa contra o
--   ano anterior. Somar a receita do segmento distorceria o resultado, porque empresas
--   entram na bolsa em anos diferentes.
CREATE OR REPLACE TABLE indicadores_validos AS
WITH reais AS (
    SELECT i.*,
           i.receita * m.fator_real AS receita_real,
           -- Capital de giro operacional = estoques + contas a receber - fornecedores.
           -- Custo de carregá-lo = capital x Selic média do ano (custo de oportunidade
           -- ou de captação), em % da receita, para comparar com a margem EBIT.
           i.estoque_medio + i.receber_medio - i.fornecedor_medio AS capital_giro,
           (i.estoque_medio + i.receber_medio - i.fornecedor_medio) * m.selic_media / 100
               / nullif(i.receita, 0) AS custo_giro
    FROM indicadores i
    JOIN macro m USING (ano)
    WHERE NOT EXISTS (
        SELECT 1 FROM qualidade q
        WHERE q.cd_cvm = i.cd_cvm AND q.ano = i.ano AND q.bloqueante
    )
)
, com_crescimento AS (
    SELECT *,
           CASE WHEN lag(ano) OVER w = ano - 1
                THEN receita_real / lag(receita_real) OVER w - 1 END AS crescimento_bruto
    FROM reais
    WINDOW w AS (PARTITION BY cd_cvm ORDER BY ano)
)
-- Variação real acima de ±40% num ano quase sempre é cisão, aquisição ou venda de
-- operação, não crescimento orgânico: fica fora da mediana de crescimento.
SELECT * EXCLUDE (crescimento_bruto),
       crescimento_bruto AS crescimento_real_informado,
       CASE WHEN abs(crescimento_bruto) <= 0.40 THEN crescimento_bruto END AS crescimento_real
FROM com_crescimento;

INSERT INTO qualidade
SELECT cd_cvm, empresa, ano, 'mudança de perímetro provável', false,
       printf('receita real variou %+.0f%% no ano; fora da mediana de crescimento',
              100 * crescimento_real_informado)
FROM indicadores_validos
WHERE abs(crescimento_real_informado) > 0.40;

CREATE OR REPLACE TABLE segmentos AS
SELECT segmento, ano,
       count(*)                  AS empresas,
       median(margem_bruta)      AS margem_bruta,
       median(margem_ebit)       AS margem_ebit,
       median(pmr)               AS pmr,
       median(pme)               AS pme,
       median(pmp)               AS pmp,
       median(ciclo_caixa)       AS ciclo_caixa,
       median(custo_giro)        AS custo_giro,
       median(crescimento_real)  AS crescimento_real
FROM indicadores_validos
GROUP BY segmento, ano
ORDER BY segmento, ano;
