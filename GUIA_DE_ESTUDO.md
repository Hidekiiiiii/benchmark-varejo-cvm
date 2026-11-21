# Guia de estudo: o benchmark do varejo por dentro

Objetivo: explicar o projeto numa entrevista, defender as escolhas de dados e de método, e fazer pequenas mudanças com segurança. Sempre que der, a comparação é com o Excel.

---

## 1. O que o projeto responde

"**Quanto do lucro operacional o capital de giro consome quando o juro sobe?**" A resposta vem de dados públicos de 24 varejistas da bolsa, de 2015 a 2025.

O projeto é um **pipeline ETL**:
- **Extrair:** baixar os arquivos da CVM e do Banco Central.
- **Carregar:** colocar tudo num banco.
- **Transformar:** limpar, calcular e conferir com SQL.

É o trabalho de um analista de dados de verdade: a fonte é pública e "suja", e o valor está em tratá-la direito antes de tirar conclusão.

## 2. Mapa dos arquivos

| Arquivo | Papel | Analogia no Excel |
|---|---|---|
| `src/benchmark/fontes.py` | Baixa as DFPs da CVM e as séries do BCB, com cache em `dados/brutos/` | "Obter dados da Web" do Power Query |
| `src/benchmark/carga.py` | Joga os arquivos brutos no DuckDB, sem transformar nada | Importar para uma aba "Bruto" |
| `sql/01_contas.sql` … `05_segmentos.sql` | As transformações, executadas em ordem alfabética | As etapas aplicadas do Power Query |
| `src/benchmark/graficos.py` | Os 3 PNG de `docs/` | Os gráficos do relatório |
| `src/benchmark/pipeline.py` | Roda tudo em 5 passos e imprime o resumo | O botão "Atualizar tudo" |
| `config/empresas.csv` | Código CVM, nome e segmento das 24 empresas | Aba de cadastro |
| `resultados/*.csv` | O que sai do pipeline | A aba final que vai para o relatório |
| `tests/test_transformacoes.py` | Roda os mesmos SQL sobre dados inventados e calculáveis à mão | Uma planilha de teste com resposta conhecida |

**A regra que organiza o projeto:**
- O Python só **busca** e **carrega** os dados.
- **Toda a regra de negócio está em SQL**, em arquivos que qualquer analista lê sem saber Python.

## 3. Extrair e carregar

**Extração** (`fontes.py`):
- **CVM:** baixa um `.zip` de DFP por ano.
- **BCB:** baixa duas séries do SGS, a 433 (IPCA mensal) e a 4189 (Selic).
- **Cache:** se o arquivo já existe em `dados/brutos/`, não baixa de novo. A primeira execução baixa cerca de 150 MB; as seguintes rodam em segundos.
- **Robustez:** `_baixar` tenta até 3 vezes, esperando um pouco mais a cada tentativa. Grava primeiro num arquivo `.parcial` e só o renomeia no fim, para que um download interrompido não deixe um zip corrompido que pareça completo.

**Carga** (`carga.py`):
- `read_csv('dfp_cia_aberta_*_con_*.csv', ...)` lê **todos os anos e demonstrações de uma vez**. São cerca de 1,9 milhão de linhas.
- `encoding='latin-1'`: os CSVs da CVM não vêm em UTF-8. Sem isso, os acentos quebram.
- `all_varchar=true`: tudo entra como texto. A conversão de tipo é feita depois, no SQL, onde dá para ver e testar.
- `union_by_name=true`: a DRE tem uma coluna que o balanço não tem (`DT_INI_EXERC`). Com essa opção, as colunas são juntadas pelo nome, e não pela posição.

**Por que DuckDB?**
- É um banco SQL que roda dentro do Python, sem servidor e sem instalação à parte.
- Lê CSV direto e é feito para análise: agrega milhões de linhas em segundos.
- Para este volume, pandas também daria conta. A vantagem do DuckDB é que a lógica fica em SQL, que é a linguagem que a maioria das áreas de dados usa.

## 4. O formato da DFP e a passagem de "longo" para "largo"

A CVM publica uma linha por **empresa × documento × conta × período**. As colunas que importam:

| Coluna | O que é |
|---|---|
| `CD_CONTA` | Código do plano padrão: `3.01` receita, `3.02` CMV, `1.01.04` estoques, `2.01.02` fornecedores… |
| `ORDEM_EXERC` | `ÚLTIMO` = o ano do documento; `PENÚLTIMO` = o ano anterior, que vem no mesmo documento para comparação |
| `VERSAO` | Cada reapresentação gera uma versão nova |
| `ESCALA_MOEDA` | `MIL` ou `UNIDADE`: umas empresas publicam em milhares, outras em reais |

**`01_contas.sql`** faz três coisas:
1. Fica só com as 10 contas e as 24 empresas usadas.
2. Multiplica por 1.000 o que está em `MIL`.
3. Fica com a **versão mais recente** de cada documento (`max(versao) OVER (PARTITION BY ...)`). Uma *window function* calcula o máximo por grupo sem agrupar as linhas, como um `MÁXIMOSES` repetido em cada linha.

**`02_indicadores.sql`** transforma o longo em largo, com uma coluna por conta:

```sql
max(valor) FILTER (WHERE conta = '3.01' AND ordem = 'ÚLTIMO') AS receita
```

É uma tabela dinâmica com uma coluna por conta, ou um `SOMASES` com dois critérios. O resultado é **uma linha por empresa e ano**.

O CMV vem **negativo** na DRE da CVM, então o código troca o sinal (`-max(...)`). Sem isso, os prazos que usam CMV sairiam negativos.

## 5. Os indicadores, com um exemplo real (Lojas Renner, 2025)

| Indicador | Fórmula | Renner 2025 |
|---|---|---|
| **PMR**, prazo médio de recebimento | contas a receber médias ÷ receita × 365 | 7.039 ÷ 15.829 × 365 = **162 dias** |
| **PME**, prazo médio de estocagem | estoque médio ÷ CMV × 365 | 1.898 ÷ 6.062 × 365 = **114 dias** |
| **PMP**, prazo médio de pagamento | fornecedores médios ÷ CMV × 365 | 1.811 ÷ 6.062 × 365 = **109 dias** |
| **Ciclo de caixa** | PME + PMR − PMP | 114 + 162 − 109 = **168 dias** |

Valores em R$ milhões. Os cálculos foram conferidos no banco do projeto.

Leitura: entre pagar o fornecedor e receber do cliente, a Renner financia 168 dias de operação. O PMR é alto porque as contas a receber incluem o crediário do cartão próprio, uma limitação que o README declara.

**Ciclo negativo (C&A, −10 dias):** o PMP de 205 dias é maior que PME + PMR (112 + 83). A C&A recebe do cliente antes de pagar o fornecedor: o fornecedor financia a operação.

**Por que estoque e fornecedor sobre CMV, e recebível sobre receita?** Porque cada saldo tem que ser comparado com o fluxo que o forma:
- o estoque sai pelo custo;
- o fornecedor é pago pelo custo das compras;
- o cliente paga pelo preço de venda.

## 6. Saldo médio, e por que o saldo inicial vem do mesmo documento

Os prazos usam **saldo médio** = (saldo final + saldo inicial) ÷ 2. Usar só o saldo de dezembro distorce: uma empresa que cresce muito tem saldo final alto e parece ter prazos mais longos do que tem.

O saldo inicial vem da coluna `PENÚLTIMO` **do mesmo documento**, e não do documento do ano anterior. Se a empresa reapresentou ou mudou de critério contábil, os dois saldos seguem a mesma regra.

Se o saldo inicial não existir (primeiro ano na bolsa), `coalesce(..._ini, ..._fim)` usa o final no lugar.

## 7. Preços constantes e juros

**Receita a preços de hoje** (`03_macro.sql`). Para comparar a receita de 2015 com a de 2025, é preciso tirar a inflação.
1. Monta um número-índice do IPCA, multiplicando (1 + variação do mês) acumulada.
2. Em SQL não existe "PRODUTO acumulado", então o código usa `exp(sum(ln(1 + x)))`. Somar logaritmos é o mesmo que multiplicar, um truque padrão.
3. `fator_real` = índice do último mês ÷ índice médio do ano. A média é usada porque a receita entra ao longo do ano inteiro, não só em dezembro.

Exemplo: o fator de 2015 é **1,718**, ou seja, R$ 1,00 de receita de 2015 vale R$ 1,72 de hoje.

**Selic:** a média anual da série 4189. Ela fica em 13,4% em 2015, cai a 4,4% em 2021 e volta a 14,3% em 2025.

**Crescimento real** (`05_segmentos.sql`) é sempre **a mesma empresa contra ela mesma no ano anterior** (`lag(...) OVER (PARTITION BY cd_cvm ORDER BY ano)`). Somar a receita do segmento distorceria o resultado: quando uma empresa abre capital, o segmento "cresce" sem ninguém ter vendido mais.

## 8. Quanto o capital de giro custa

```
capital de giro operacional = estoques + contas a receber − fornecedores
custo do giro (% da receita) = capital de giro × Selic média ÷ receita
```

Renner 2025: (1.898 + 7.039 − 1.811) = R$ 7.126 mi × 14,3% = R$ 1.020 mi, que é **6,4% da receita**, contra uma margem EBIT de 11,4%.

A pergunta que isso responde: "se o dinheiro preso no giro rendesse a Selic, ou se fosse financiado a ela, quanto da margem iria embora?".

É uma **simplificação**, e o README diz isso. O custo real de captação de cada empresa é diferente da Selic. Mas a ordem de grandeza permite comparar segmentos:

| Segmento (mediana 2025) | Ciclo | Custo do giro | Margem EBIT |
|---|---|---|---|
| Moda e acessórios | 167 dias | 5,5% | 13,1% |
| Supermercados e atacarejo | 26 dias | 1,0% | 5,9% |
| Quero-Quero (uma empresa) | 190 dias | 7,3% | 0,5% |

## 9. As conferências de qualidade

`04_qualidade.sql` grava cada problema numa tabela `qualidade`, com a regra, o detalhe e se ele é **bloqueante**. Uma linha bloqueante tira aquela empresa-ano das medianas.

| Tipo | Regras | Por quê |
|---|---|---|
| **Bloqueia** | conta essencial ausente; DRE não fecha (1%); balanço não fecha (0,5%); margem bruta fora de 0–100% | Se o dado básico está errado, qualquer indicador está errado |
| **Só registra** | ciclo atípico; reapresentação; escala em unidades; mudança de perímetro provável | Pode ser do negócio (a Vivara tem estoque longo de joias) ou só informação |

A mudança de perímetro (receita real variando mais de ±40% no ano) **não exclui a linha**. Ela tira só aquele ano da mediana de **crescimento**: cisão, fusão ou venda de operação não é crescimento orgânico. Exemplos que a regra marcou:
- a fusão Americanas + B2W (+107% em 2021);
- a cisão do Assaí no GPA (−69% em 2022).

**Um fato para a entrevista:** na base atual, **nenhuma regra bloqueante dispara**, e as 214 empresas-ano entram nas medianas. A DRE e o balanço da CVM fecham exatamente (testei apertando as tolerâncias quase a zero). As regras existem porque o pipeline precisa continuar seguro quando entrar uma empresa nova ou um ano novo, e os testes provam que elas funcionam com dados inventados.

## 10. Mediana, painel fixo e correlação

- **Mediana em vez de média:** com 2 a 7 empresas por segmento, um extremo puxa a média. Em eletro e departamento, a mediana do ciclo em 2025 é 18,5 dias; a média seria 56,6, puxada pela Quero-Quero (190 dias).
- **Painel fixo** (`graficos.py`, função `selic_e_prazos`): o gráfico de Selic × prazos usa só as **12 empresas com dados em todos os anos** (`HAVING count(*) = ...`). Sem isso, a mediana mudaria só porque empresas entraram ou saíram da bolsa, e não porque os prazos mudaram.
- **Correlação não é causa.** O README diz que o prazo de recebimento acompanhou o juro: o ciclo foi de 49 dias (2015) a 70 (2021) e voltou a 45 (2025). Mas a pandemia também alongou prazos. Dizer isso antes que perguntem mostra maturidade.

## 11. Os testes

`python -m pytest`: 10 testes, **sem internet e sem os arquivos da CVM**. O `fixture` monta tabelas "brutas" no mesmo formato da DFP, com 5 empresas inventadas e calculáveis à mão, e roda **os mesmos arquivos SQL** do pipeline:

| Empresa | O que ela tem | O que o teste confere |
|---|---|---|
| Alfa | Reapresentação em 2024 (a versão 2 corrige a receita) | Que vale a versão 2 |
| Beta | Publica em reais (`UNIDADE`) e a DRE não fecha | Que a escala é convertida e a regra bloqueia |
| Gama | CMV com sinal trocado, margem bruta de 160% | Que a regra "margem impossível" pega |
| Delta | Receita dobra de um ano para o outro | Que sai da mediana de crescimento |
| 99 | Está fora da lista de empresas | Que é ignorada |

Além disso, o IPCA de teste é de 1% ao mês em 2023 e 0% em 2024, e a Selic é de 10%. Assim, o fator de inflação e o custo do giro têm resposta conhecida.

**Os testes pegam erro de verdade.** Testei duas mutações numa cópia:
- tirar o filtro de versão mais recente derruba 5 dos 10 testes;
- trocar o saldo médio pelo saldo final derruba 2.

## 12. Cinco exercícios

Para recalcular sem baixar nada de novo, rode `python -m src.benchmark.pipeline`: os arquivos já estão no cache. Os resultados citados foram conferidos.

O pipeline regrava `resultados/` e `docs/`. Depois de cada exercício, desfaça as mudanças:

```
git checkout -- sql config resultados docs
```

1. **Mediana × média (fácil).** Em `sql/05_segmentos.sql`, linha 52, troque `median(ciclo_caixa)` por `avg(ciclo_caixa)`. Em 2025, o ciclo de eletro e departamento salta de **18,5 para 56,6 dias**, e o de moda de 166,9 para 177,9. Descubra qual empresa puxou cada um.
2. **Apertar o ciclo atípico (fácil).** Em `sql/04_qualidade.sql`, linha 44, troque `365` por `200`. Os registros de "ciclo atípico" passam de **7** (só Vivara) para **18**, e entram Riachuelo e Veste. Como a regra só registra, as medianas não mudam. Por quê?
3. **Apertar a regra de perímetro (médio).** Em `sql/05_segmentos.sql`, linhas 34 e 42, troque `0.40` por `0.30`. Os anos marcados passam de **9 para 13**. Olhe os novos em `resultados/qualidade.csv` e decida: aquisição ou crescimento orgânico forte?
4. **Quebrar a versão de propósito (médio).** Em `sql/01_contas.sql`, apague a linha 24 (`WHERE versao = versao_max`), deixando o `;`. Rode `python -m pytest`: **5 testes falham**. Leia `test_usa_a_versao_mais_recente` e explique o que aconteceria com a receita de uma empresa que reapresentou.
5. **Acrescentar uma empresa (médio).** Inclua uma linha em `config/empresas.csv` com o código CVM de outra varejista. Encontre o código no cadastro de companhias abertas em dados.cvm.gov.br. Rode o pipeline e veja se ela passa nas regras de qualidade e para qual segmento a mediana mudou.

## 13. Perguntas de entrevista

1. **O que é ciclo de caixa e por que importa?** São os dias entre pagar o fornecedor e receber do cliente: PME + PMR − PMP. É o tempo em que a empresa financia a operação com dinheiro próprio ou emprestado, e o juro torna isso caro.
2. **Por que DuckDB e SQL?** É um banco que roda dentro do Python, lê CSV direto e agrega milhões de linhas rápido. A regra de negócio em SQL fica legível para qualquer analista e testável.
3. **Como você tratou a qualidade dos dados públicos?** São quatro regras que bloqueiam (contas ausentes, DRE e balanço que não fecham, margem impossível) e quatro que só registram. Tudo fica numa tabela de qualidade exportada.
4. **Por que saldo médio?** O saldo de dezembro distorce em quem cresce ou é sazonal. O saldo inicial vem do mesmo documento, para seguir o mesmo critério contábil.
5. **Como compara receita de anos diferentes?** A preços constantes, pelo IPCA médio do ano, e sempre a mesma empresa contra ela mesma. Somar o segmento misturaria entrada e saída de empresas na bolsa.
6. **O que é a regra de perímetro e qual o limite dela?** Uma variação real acima de ±40% sai da mediana de crescimento, porque costuma ser fusão ou cisão. É heurística: também marca crescimento orgânico forte, como o Magazine Luiza em 2020.
7. **A Selic causou o aumento dos prazos?** Os dados mostram que os dois andaram juntos, mas a pandemia também alongou prazos. Para falar em causa, eu precisaria de um desenho que separasse os efeitos.
8. **Como você testa um pipeline que depende de dados externos?** Com dados inventados no mesmo formato da fonte, calculáveis à mão, rodando os mesmos SQL. Os testes não dependem de internet e pegam erros reais, o que conferi introduzindo mutações.
9. **O que faria com mais tempo?** Separar o braço financeiro (cartão próprio) das contas a receber, usar dados trimestrais (ITR) para ver a sazonalidade e usar o custo de captação de cada empresa em vez da Selic.
10. **Como você usou IA no projeto?** Escreva sua resposta: o que você definiu (a pergunta, as empresas, os segmentos), o que conferiu nos números e como a tabela de qualidade e os testes validaram o resultado.
