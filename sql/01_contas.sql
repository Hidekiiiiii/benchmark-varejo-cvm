-- 01. Contas usadas, já tratadas.
-- * Só as empresas da lista (config/empresas.csv) e as contas do plano padrão da CVM.
-- * Valores em reais: a CVM publica uns em "MIL" e outros em "UNIDADE".
-- * Reapresentações: cada DFP pode ter várias versões; vale a mais recente.
CREATE OR REPLACE TABLE contas AS
WITH base AS (
    SELECT
        CAST(CD_CVM AS INTEGER)                        AS cd_cvm,
        CAST(DT_REFER AS DATE)                         AS dt_refer,
        CAST(VERSAO AS INTEGER)                        AS versao,
        ORDEM_EXERC                                    AS ordem,      -- ÚLTIMO = ano do documento; PENÚLTIMO = ano anterior
        demonstracao,
        CD_CONTA                                       AS conta,
        ESCALA_MOEDA                                   AS escala,
        CAST(VL_CONTA AS DOUBLE)
          * CASE ESCALA_MOEDA WHEN 'MIL' THEN 1000 ELSE 1 END AS valor
    FROM bruto_dfp
    WHERE CD_CONTA IN ('1', '2', '1.01.03', '1.01.04', '2.01.02',
                       '3.01', '3.02', '3.03', '3.05', '3.11')
      AND CAST(CD_CVM AS INTEGER) IN (SELECT cd_cvm FROM empresas)
)
SELECT * EXCLUDE (versao_max)
FROM (SELECT *, max(versao) OVER (PARTITION BY cd_cvm, dt_refer) AS versao_max FROM base)
WHERE versao = versao_max;
