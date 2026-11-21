-- 04. Conferências de qualidade. Cada linha é um problema encontrado.
-- Linhas com problema "bloqueante" ficam fora das medianas por segmento (ver 05).
CREATE OR REPLACE TABLE qualidade AS
-- Contas essenciais ausentes: sem elas o indicador não existe.
SELECT cd_cvm, empresa, ano, 'conta ausente' AS regra, true AS bloqueante,
       'falta: ' || concat_ws(', ',
            CASE WHEN receita       IS NULL THEN 'receita' END,
            CASE WHEN cmv           IS NULL THEN 'CMV' END,
            CASE WHEN estoque_medio IS NULL THEN 'estoques' END,
            CASE WHEN receber_medio IS NULL THEN 'contas a receber' END,
            CASE WHEN fornecedor_medio IS NULL THEN 'fornecedores' END) AS detalhe
FROM indicadores
WHERE receita IS NULL OR cmv IS NULL OR estoque_medio IS NULL
   OR receber_medio IS NULL OR fornecedor_medio IS NULL

UNION ALL
-- Receita - CMV tem de bater com o Resultado Bruto informado.
SELECT cd_cvm, empresa, ano, 'DRE não fecha', true,
       printf('receita - CMV - lucro bruto = %.1f%% da receita',
              100 * (receita - cmv - lucro_bruto) / receita)
FROM indicadores
WHERE abs(receita - cmv - lucro_bruto) > 0.01 * abs(receita)

UNION ALL
-- Ativo total = passivo total + patrimônio líquido.
SELECT cd_cvm, empresa, ano, 'balanço não fecha', true,
       printf('ativo - passivo = %.2f%% do ativo', 100 * (ativo_total - passivo_total) / ativo_total)
FROM indicadores
WHERE abs(ativo_total - passivo_total) > 0.005 * abs(ativo_total)

UNION ALL
-- Margem bruta fora de 0-100% é impossível: erro de dado.
SELECT cd_cvm, empresa, ano, 'margem impossível', true,
       printf('margem bruta %.0f%%', 100 * margem_bruta)
FROM indicadores
WHERE margem_bruta NOT BETWEEN 0 AND 1

UNION ALL
-- Ciclo muito longo ou muito negativo: pode ser do negócio (joalheria tem estoque
-- longo), então só fica registrado. A mediana do segmento resiste a esses casos.
SELECT cd_cvm, empresa, ano, 'ciclo atípico', false,
       printf('ciclo de caixa de %.0f dias', ciclo_caixa)
FROM indicadores
WHERE ciclo_caixa NOT BETWEEN -180 AND 365

UNION ALL
-- Informativos: não excluem a linha, mas ficam no registro.
SELECT cd_cvm, empresa, ano, 'reapresentação', false,
       'vale a versão ' || versao || ' do documento'
FROM indicadores WHERE versao > 1

UNION ALL
SELECT cd_cvm, empresa, ano, 'escala em unidades', false,
       'valores publicados em reais (não em milhares); convertidos'
FROM indicadores WHERE escala = 'UNIDADE';
