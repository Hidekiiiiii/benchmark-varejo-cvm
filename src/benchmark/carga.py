"""Carga: coloca os arquivos brutos no DuckDB, sem transformar nada.

As transformações ficam nos arquivos .sql de sql/, executados em ordem.
"""
from __future__ import annotations

from pathlib import Path

import duckdb


def carregar_brutos(con: duckdb.DuckDBPyConnection, pasta_cvm: Path, arquivos_bcb: dict[str, Path],
                    arquivo_empresas: Path) -> None:
    # DFP: todos os anos e demonstrações numa tabela só. Os CSVs da CVM vêm em
    # latin-1, separados por ";" e com colunas que variam entre demonstrações
    # (a DRE tem DT_INI_EXERC; o balanço, não) -> union_by_name.
    padrao = (pasta_cvm / "dfp_cia_aberta_*_con_*.csv").as_posix()
    con.execute(f"""
        CREATE OR REPLACE TABLE bruto_dfp AS
        SELECT *, regexp_extract(filename, '(DRE|BPA|BPP)_con', 1) AS demonstracao
        FROM read_csv('{padrao}', delim=';', header=true, encoding='latin-1',
                      all_varchar=true, union_by_name=true, filename=true)
    """)

    for nome, arq in arquivos_bcb.items():
        con.execute(f"""
            CREATE OR REPLACE TABLE bruto_{nome} AS
            SELECT strptime(data, '%d/%m/%Y')::DATE AS data, CAST(valor AS DOUBLE) AS valor
            FROM read_json('{arq.as_posix()}', columns={{'data': 'VARCHAR', 'valor': 'VARCHAR'}})
        """)

    con.execute(f"""
        CREATE OR REPLACE TABLE empresas AS
        SELECT CAST(cd_cvm AS INTEGER) AS cd_cvm, empresa, segmento
        FROM read_csv('{arquivo_empresas.as_posix()}', header=true, all_varchar=true)
    """)


def executar_sql(con: duckdb.DuckDBPyConnection, pasta_sql: Path) -> list[str]:
    """Executa os .sql em ordem alfabética (01_, 02_...). Devolve os nomes executados."""
    feitos = []
    for arq in sorted(pasta_sql.glob("*.sql")):
        con.execute(arq.read_text(encoding="utf-8"))
        feitos.append(arq.name)
    return feitos
