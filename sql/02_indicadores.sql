-- 02. Uma linha por empresa e ano, com os indicadores de controladoria.
-- Saldos médios do ano = (saldo final + saldo inicial) / 2. O saldo inicial vem da
-- coluna PENÚLTIMO do mesmo documento, então os dois saldos seguem o mesmo critério contábil.
CREATE OR REPLACE TABLE indicadores AS
WITH largo AS (
    SELECT
        cd_cvm,
        year(dt_refer) AS ano,
        any_value(versao) AS versao,
        any_value(escala) AS escala,
        max(valor) FILTER (WHERE conta = '3.01'    AND ordem = 'ÚLTIMO')    AS receita,
        -max(valor) FILTER (WHERE conta = '3.02'   AND ordem = 'ÚLTIMO')    AS cmv,        -- vem negativo na DRE
        max(valor) FILTER (WHERE conta = '3.03'    AND ordem = 'ÚLTIMO')    AS lucro_bruto,
        max(valor) FILTER (WHERE conta = '3.05'    AND ordem = 'ÚLTIMO')    AS ebit,
        max(valor) FILTER (WHERE conta = '3.11'    AND ordem = 'ÚLTIMO')    AS lucro_liquido,
        max(valor) FILTER (WHERE conta = '1'       AND ordem = 'ÚLTIMO')    AS ativo_total,
        max(valor) FILTER (WHERE conta = '2'       AND ordem = 'ÚLTIMO')    AS passivo_total,
        max(valor) FILTER (WHERE conta = '1.01.03' AND ordem = 'ÚLTIMO')    AS receber_fim,
        max(valor) FILTER (WHERE conta = '1.01.03' AND ordem = 'PENÚLTIMO') AS receber_ini,
        max(valor) FILTER (WHERE conta = '1.01.04' AND ordem = 'ÚLTIMO')    AS estoque_fim,
        max(valor) FILTER (WHERE conta = '1.01.04' AND ordem = 'PENÚLTIMO') AS estoque_ini,
        max(valor) FILTER (WHERE conta = '2.01.02' AND ordem = 'ÚLTIMO')    AS fornecedor_fim,
        max(valor) FILTER (WHERE conta = '2.01.02' AND ordem = 'PENÚLTIMO') AS fornecedor_ini
    FROM contas
    GROUP BY cd_cvm, year(dt_refer)
),
medias AS (
    SELECT *,
        (receber_fim    + coalesce(receber_ini,    receber_fim))    / 2 AS receber_medio,
        (estoque_fim    + coalesce(estoque_ini,    estoque_fim))    / 2 AS estoque_medio,
        (fornecedor_fim + coalesce(fornecedor_ini, fornecedor_fim)) / 2 AS fornecedor_medio
    FROM largo
)
SELECT
    m.cd_cvm, e.empresa, e.segmento, m.ano, m.versao, m.escala,
    m.receita, m.cmv, m.lucro_bruto, m.ebit, m.lucro_liquido, m.ativo_total, m.passivo_total,
    m.receber_medio, m.estoque_medio, m.fornecedor_medio,
    m.lucro_bruto   / nullif(m.receita, 0)              AS margem_bruta,
    m.ebit          / nullif(m.receita, 0)              AS margem_ebit,
    m.lucro_liquido / nullif(m.receita, 0)              AS margem_liquida,
    m.receber_medio    / nullif(m.receita, 0) * 365     AS pmr,   -- prazo médio de recebimento (dias)
    m.estoque_medio    / nullif(m.cmv, 0)     * 365     AS pme,   -- prazo médio de estocagem (dias)
    m.fornecedor_medio / nullif(m.cmv, 0)     * 365     AS pmp,   -- prazo médio de pagamento (dias)
    (m.estoque_medio / nullif(m.cmv, 0) + m.receber_medio / nullif(m.receita, 0)
       - m.fornecedor_medio / nullif(m.cmv, 0)) * 365   AS ciclo_caixa
FROM medias m
JOIN empresas e USING (cd_cvm);
