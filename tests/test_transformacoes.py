"""Testes das transformações SQL com dados sintéticos pequenos, calculáveis à mão.

Roda os mesmos arquivos de sql/ do pipeline sobre tabelas "brutas" montadas aqui,
sem internet e sem os arquivos da CVM.
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import pytest

from src.benchmark.carga import executar_sql

SQL = Path(__file__).resolve().parents[1] / "sql"


def linhas(cd, ano, versao, escala, contas_ult, contas_pen=None):
    """Gera linhas no formato da DFP para uma empresa-ano."""
    out = []
    for ordem, contas in (("ÚLTIMO", contas_ult), ("PENÚLTIMO", contas_pen or {})):
        for conta, valor in contas.items():
            out.append({
                "CD_CVM": f"{cd:06d}", "DT_REFER": f"{ano}-12-31", "VERSAO": str(versao),
                "ORDEM_EXERC": ordem, "CD_CONTA": conta, "ESCALA_MOEDA": escala,
                "VL_CONTA": str(valor), "demonstracao": "DRE",
            })
    return out


def balanco_ok(**k):
    """Contas mínimas de um ano 'saudável' (em milhares quando escala = MIL)."""
    base = {"3.01": 1000, "3.02": -600, "3.03": 400, "3.05": 100, "3.11": 60,
            "1": 2000, "2": 2000, "1.01.03": 100, "1.01.04": 120, "2.01.02": 90}
    base.update(k)
    return base


@pytest.fixture
def con():
    c = duckdb.connect()
    brutos = []
    # Empresa 1: dois anos; o de 2024 tem uma reapresentação (versão 2 corrige a receita).
    brutos += linhas(1, 2023, 1, "MIL", balanco_ok(), balanco_ok())
    brutos += linhas(1, 2024, 1, "MIL", balanco_ok(**{"3.01": 999_999}), balanco_ok())
    brutos += linhas(1, 2024, 2, "MIL",
                     balanco_ok(**{"1.01.03": 140, "1.01.04": 180, "2.01.02": 150}),
                     balanco_ok())
    # Empresa 2: publica em UNIDADE (reais) e a DRE não fecha (lucro bruto errado).
    brutos += linhas(2, 2024, 1, "UNIDADE",
                     {k: v * 1000 for k, v in balanco_ok(**{"3.03": 300}).items()})
    # Empresa 3: margem bruta impossível (CMV positivo -> lucro bruto > receita).
    brutos += linhas(3, 2024, 1, "MIL", balanco_ok(**{"3.02": 600, "3.03": 1600}))
    # Empresa 4: receita dobra de um ano para o outro (cisão/aquisição provável).
    brutos += linhas(4, 2023, 1, "MIL", balanco_ok())
    brutos += linhas(4, 2024, 1, "MIL", balanco_ok(**{"3.01": 2000, "3.02": -1200, "3.03": 800}))
    # Empresa 99: fora da lista de empresas -> deve ser ignorada.
    brutos += linhas(99, 2024, 1, "MIL", balanco_ok())

    c.register("df_bruto", pd.DataFrame(brutos))
    c.execute("CREATE TABLE bruto_dfp AS SELECT * FROM df_bruto")
    c.execute("""CREATE TABLE empresas AS SELECT * FROM (VALUES
        (1, 'Alfa', 'Seg A'), (2, 'Beta', 'Seg A'), (3, 'Gama', 'Seg B'), (4, 'Delta', 'Seg B'))
        t(cd_cvm, empresa, segmento)""")
    # IPCA de 1% ao mês em 2023 e 0% em 2024; Selic de 10% a.a.
    meses = pd.date_range("2023-01-01", "2024-12-01", freq="MS")
    c.register("df_ipca", pd.DataFrame({"data": meses.date, "valor": [1.0] * 12 + [0.0] * 12}))
    c.register("df_selic", pd.DataFrame({"data": meses.date, "valor": [10.0] * 24}))
    c.execute("CREATE TABLE bruto_ipca_mensal AS SELECT * FROM df_ipca")
    c.execute("CREATE TABLE bruto_selic_anual AS SELECT * FROM df_selic")
    executar_sql(c, SQL)
    return c


def um(con, sql, *params):
    return con.execute(sql, list(params)).fetchone()


def test_ignora_empresas_fora_da_lista(con):
    assert um(con, "SELECT count(*) FROM indicadores WHERE cd_cvm = 99")[0] == 0


def test_usa_a_versao_mais_recente(con):
    receita, versao = um(con, "SELECT receita, versao FROM indicadores WHERE cd_cvm = 1 AND ano = 2024")
    assert versao == 2
    assert receita == 1_000_000  # 1.000 mil (não os 999.999 mil da versão 1)


def test_converte_escala_para_reais(con):
    # Empresa 2 publica em reais; empresa 1, em milhares. As duas devem ficar em reais.
    r1 = um(con, "SELECT receita FROM indicadores WHERE cd_cvm = 1 AND ano = 2023")[0]
    r2 = um(con, "SELECT receita FROM indicadores WHERE cd_cvm = 2 AND ano = 2024")[0]
    assert r1 == r2 == 1_000_000


def test_prazos_com_saldo_medio(con):
    pme, pmr, pmp, ciclo, mb = um(con, """
        SELECT pme, pmr, pmp, ciclo_caixa, margem_bruta FROM indicadores WHERE cd_cvm = 1 AND ano = 2024""")
    # Saldos médios: estoque (180+120)/2 = 150; receber (140+100)/2 = 120; fornecedor (150+90)/2 = 120.
    assert pme == pytest.approx(150 / 600 * 365)
    assert pmr == pytest.approx(120 / 1000 * 365)
    assert pmp == pytest.approx(120 / 600 * 365)
    assert ciclo == pytest.approx(pme + pmr - pmp)
    assert mb == pytest.approx(0.4)


def test_cmv_fica_positivo(con):
    assert um(con, "SELECT cmv FROM indicadores WHERE cd_cvm = 1 AND ano = 2023")[0] == 600_000


def test_regras_de_qualidade(con):
    regras = {(r[0], r[1]) for r in con.execute("SELECT cd_cvm, regra FROM qualidade").fetchall()}
    assert (2, "DRE não fecha") in regras
    assert (2, "escala em unidades") in regras
    assert (3, "margem impossível") in regras
    assert (1, "reapresentação") in regras
    assert (4, "mudança de perímetro provável") in regras


def test_bloqueantes_ficam_fora_das_medianas(con):
    validas = {r[0] for r in con.execute("SELECT DISTINCT cd_cvm FROM indicadores_validos").fetchall()}
    assert validas == {1, 4}  # 2 (DRE não fecha) e 3 (margem impossível) saem


def test_crescimento_real_e_perimetro(con):
    # 2023 -> 2024: inflação de 2024 = 0%, então fator_real de 2024 = 1 e o de 2023 > 1.
    c1 = um(con, "SELECT crescimento_real FROM indicadores_validos WHERE cd_cvm = 1 AND ano = 2024")[0]
    assert c1 < 0  # mesma receita nominal, mas 2023 vale mais a preços de hoje
    informado, usado = um(con, """SELECT crescimento_real_informado, crescimento_real
                                  FROM indicadores_validos WHERE cd_cvm = 4 AND ano = 2024""")
    assert informado > 0.40 and usado is None


def test_macro(con):
    ipca23, selic23, fator24 = um(con, """SELECT (SELECT ipca_ano FROM macro WHERE ano = 2023),
        (SELECT selic_media FROM macro WHERE ano = 2023), (SELECT fator_real FROM macro WHERE ano = 2024)""")
    assert ipca23 == pytest.approx(100 * (1.01 ** 12 - 1))
    assert selic23 == pytest.approx(10)
    assert fator24 == pytest.approx(1)  # índice parado o ano todo em 2024


def test_custo_do_giro(con):
    custo = um(con, "SELECT custo_giro FROM indicadores_validos WHERE cd_cvm = 1 AND ano = 2024")[0]
    # capital de giro = 150 + 120 - 120 = 150 mil; x 10% / 1.000 mil = 1,5% da receita
    assert custo == pytest.approx(0.015)
