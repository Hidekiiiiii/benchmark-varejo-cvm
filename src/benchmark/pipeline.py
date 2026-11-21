"""Roda o pipeline inteiro: extrair -> carregar -> transformar -> conferir -> exportar.

Uso (na raiz do projeto):
    python -m src.benchmark.pipeline              # 2015 a 2025
    python -m src.benchmark.pipeline --ano-fim 2024
"""
from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

from . import carga, fontes, graficos

RAIZ = Path(__file__).resolve().parents[2]
BRUTOS = RAIZ / "dados" / "brutos"
BANCO = RAIZ / "dados" / "benchmark.duckdb"
RESULTADOS = RAIZ / "resultados"


def rodar(ano_ini: int, ano_fim: int, banco: Path = BANCO) -> duckdb.DuckDBPyConnection:
    print(f"1/5 Baixando DFP da CVM ({ano_ini}-{ano_fim}) e séries do BCB...")
    for ano in range(ano_ini, ano_fim + 1):
        fontes.baixar_dfp(ano, BRUTOS / "cvm")
    bcb = fontes.baixar_bcb(BRUTOS / "bcb", ano_ini, ano_fim)

    print("2/5 Carregando no DuckDB...")
    banco.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(banco))
    carga.carregar_brutos(con, BRUTOS / "cvm", bcb, RAIZ / "config" / "empresas.csv")
    n = con.execute("SELECT count(*) FROM bruto_dfp").fetchone()[0]
    print(f"    {n:,} linhas brutas".replace(",", "."))

    print("3/5 Transformando (sql/)...")
    for nome in carga.executar_sql(con, RAIZ / "sql"):
        print(f"    {nome}")

    print("4/5 Conferindo a qualidade dos dados...")
    for regra, bloq, qtd in con.execute("""
        SELECT regra, bloqueante, count(*) FROM qualidade GROUP BY ALL ORDER BY bloqueante DESC, regra
    """).fetchall():
        print(f"    {'[exclui]' if bloq else '[info]   '} {regra}: {qtd}")
    total, validas = con.execute(
        "SELECT (SELECT count(*) FROM indicadores), (SELECT count(*) FROM indicadores_validos)").fetchone()
    print(f"    {validas} de {total} empresa-ano entram nas medianas")

    print("5/5 Exportando resultados e gráficos...")
    RESULTADOS.mkdir(exist_ok=True)
    for tabela in ("indicadores", "segmentos", "qualidade", "macro"):
        con.execute(f"COPY (SELECT * FROM {tabela}) TO '{(RESULTADOS / f'{tabela}.csv').as_posix()}' (HEADER)")
    graficos.gerar_todos(con, RAIZ / "docs")
    print("Pronto.")
    return con


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ano-ini", type=int, default=2015)
    p.add_argument("--ano-fim", type=int, default=2025)
    a = p.parse_args()
    rodar(a.ano_ini, a.ano_fim).close()


if __name__ == "__main__":
    main()
