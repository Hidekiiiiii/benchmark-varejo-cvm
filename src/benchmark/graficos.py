"""Gráficos do relatório (matplotlib -> PNG em docs/).

Paleta categórica fixa (validada para daltonismo nas três primeiras posições):
azul, laranja, verde-água. Texto sempre em tinta neutra, nunca na cor da série.
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

AZUL, LARANJA, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
FUNDO, TINTA, TINTA_2, GRADE = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"

plt.rcParams.update({
    "figure.facecolor": FUNDO, "axes.facecolor": FUNDO, "savefig.facecolor": FUNDO,
    "font.family": "DejaVu Sans", "font.size": 10,
    "text.color": TINTA, "axes.labelcolor": TINTA_2,
    "xtick.color": TINTA_2, "ytick.color": TINTA_2,
    "axes.edgecolor": GRADE, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "axes.axisbelow": True, "grid.color": GRADE, "grid.linewidth": 0.8,
    "axes.titleweight": "bold", "axes.titlesize": 13, "axes.titlelocation": "left",
})


def _titulo(fig, titulo: str, subtitulo: str) -> None:
    fig.text(0.012, 0.975, titulo, fontsize=14, fontweight="bold", va="top", color=TINTA)
    fig.text(0.012, 0.925, subtitulo, fontsize=10, va="top", color=TINTA_2)


def _fonte(fig, texto: str = "Fonte: CVM (DFP consolidada) e Banco Central (SGS). Elaboração própria.") -> None:
    fig.text(0.012, 0.012, texto, fontsize=8, color=TINTA_2)


def ciclo_por_empresa(con: duckdb.DuckDBPyConnection, pasta: Path) -> Path:
    """Barras horizontais: PME e PMR somam dias; PMP (crédito do fornecedor) subtrai."""
    ano = con.execute("SELECT max(ano) FROM indicadores_validos").fetchone()[0]
    df = con.execute("""
        SELECT empresa, segmento, pme, pmr, pmp, ciclo_caixa
        FROM indicadores_validos WHERE ano = ? ORDER BY ciclo_caixa
    """, [ano]).df()
    fig, ax = plt.subplots(figsize=(10, 0.38 * len(df) + 1.8))
    fig.subplots_adjust(left=0.30, right=0.97, top=1 - 1.05 / fig.get_figheight(),
                        bottom=0.75 / fig.get_figheight())
    y = range(len(df))
    alt = 0.62
    ax.barh(y, df.pme, height=alt, color=AZUL, label="Estoque (PME)", edgecolor=FUNDO, linewidth=1)
    ax.barh(y, df.pmr, left=df.pme, height=alt, color=AQUA, label="Recebimento (PMR)",
            edgecolor=FUNDO, linewidth=1)
    ax.barh(y, -df.pmp, height=alt, color=LARANJA, label="Prazo do fornecedor (PMP)",
            edgecolor=FUNDO, linewidth=1)
    ax.scatter(df.ciclo_caixa, list(y), s=36, color=TINTA, zorder=3, label="Ciclo de caixa",
               edgecolors=FUNDO, linewidths=1.5)
    for i, r in df.iterrows():
        ax.text(r.pme + r.pmr + 8, i, f"{int(round(r.ciclo_caixa)) + 0} dias", va="center", fontsize=8.5, color=TINTA_2)
    ax.set_yticks(list(y), [f"{e}  ·  {s}" for e, s in zip(df.empresa, df.segmento)], fontsize=9)
    ax.axvline(0, color=TINTA_2, linewidth=1)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("dias")
    ax.set_xlim(-df.pmp.max() - 20, (df.pme + df.pmr).max() + 90)
    ax.legend(loc="lower right", frameon=False, fontsize=8.5)
    _titulo(fig, f"Ciclo de caixa por empresa, {ano}",
            "Ciclo = dias de estoque + dias para receber − dias para pagar o fornecedor (saldos médios do ano)")
    _fonte(fig)
    arq = pasta / "ciclo_por_empresa.png"
    fig.savefig(arq, dpi=150)
    plt.close(fig)
    return arq


def selic_e_prazos(con: duckdb.DuckDBPyConnection, pasta: Path) -> Path:
    """Dois painéis com o mesmo eixo de tempo (sem eixo duplo): Selic em cima, prazos embaixo.
    Painel fixo: só empresas com todos os anos, para a composição não mudar a mediana."""
    df = con.execute("""
        WITH painel AS (
            SELECT cd_cvm FROM indicadores_validos GROUP BY cd_cvm
            HAVING count(*) = (SELECT count(DISTINCT ano) FROM indicadores_validos)
        )
        SELECT v.ano, count(*) AS n, median(v.ciclo_caixa) AS ciclo, median(v.pmr) AS pmr,
               any_value(m.selic_media) AS selic
        FROM indicadores_validos v JOIN painel USING (cd_cvm) JOIN macro m USING (ano)
        GROUP BY v.ano ORDER BY v.ano
    """).df()
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 6.6), sharex=True,
                                 gridspec_kw={"height_ratios": [1, 1.6], "hspace": 0.18})
    fig.subplots_adjust(left=0.08, right=0.9, top=0.84, bottom=0.09)
    a1.bar(df.ano, df.selic, color=AZUL, width=0.55)
    for x, v in zip(df.ano, df.selic):
        a1.text(x, v + 0.4, f"{v:.1f}%".replace(".", ","), ha="center", fontsize=8, color=TINTA_2)
    a1.set_ylabel("Selic média (% a.a.)")
    a1.set_ylim(0, df.selic.max() * 1.25)
    a1.grid(axis="x", visible=False)

    for col, cor, nome in (("ciclo", TINTA, "Ciclo de caixa"), ("pmr", AQUA, "Prazo de recebimento (PMR)")):
        a2.plot(df.ano, df[col], color=cor, linewidth=2, marker="o", markersize=5,
                markeredgecolor=FUNDO, markeredgewidth=1.5, label=nome)
        a2.text(df.ano.iloc[-1] + 0.15, df[col].iloc[-1], nome.split(" (")[0], va="center", fontsize=9, color=TINTA_2)
    pico = df.loc[df.ciclo.idxmax()]
    a2.annotate(f"{pico.ciclo:.0f} dias em {int(pico.ano)}", (pico.ano, pico.ciclo), (pico.ano - 2.3, pico.ciclo + 6),
                fontsize=9, color=TINTA_2, arrowprops={"arrowstyle": "-", "color": TINTA_2, "lw": 0.8})
    a2.set_ylabel("dias (mediana)")
    a2.set_ylim(0, max(df.ciclo.max(), df.pmr.max()) * 1.25)
    a2.legend(loc="lower left", frameon=False, fontsize=8.5)
    a2.set_xticks(df.ano)
    _titulo(fig, "Com juro baixo, o varejo esticou o prazo; com juro alto, encurtou",
            f"Mediana de {int(df.n.iloc[0])} varejistas listados com dados em todos os anos de "
            f"{int(df.ano.iloc[0])} a {int(df.ano.iloc[-1])}")
    _fonte(fig)
    arq = pasta / "selic_e_prazos.png"
    fig.savefig(arq, dpi=150)
    plt.close(fig)
    return arq


def custo_do_giro(con: duckdb.DuckDBPyConnection, pasta: Path) -> Path:
    """Por segmento: margem EBIT x custo de carregar o capital de giro à Selic, em % da receita."""
    ano = con.execute("SELECT max(ano) FROM segmentos").fetchone()[0]
    df = con.execute("""
        SELECT segmento, empresas, margem_ebit, custo_giro FROM segmentos WHERE ano = ?
        ORDER BY custo_giro
    """, [ano]).df()
    selic = con.execute("SELECT selic_media FROM macro WHERE ano = ?", [ano]).fetchone()[0]
    fig, ax = plt.subplots(figsize=(10, 5.2))
    fig.subplots_adjust(left=0.27, right=0.95, top=0.80, bottom=0.12)
    y = range(len(df))
    h = 0.36
    ax.barh([i + h / 2 for i in y], 100 * df.margem_ebit, height=h, color=AZUL, label="Margem EBIT",
            edgecolor=FUNDO, linewidth=1)
    ax.barh([i - h / 2 for i in y], 100 * df.custo_giro, height=h, color=LARANJA,
            label="Custo do capital de giro à Selic", edgecolor=FUNDO, linewidth=1)
    for i, r in df.iterrows():
        ax.text(100 * r.margem_ebit + 0.2, i + h / 2, f"{100 * r.margem_ebit:.1f}%".replace(".", ","),
                va="center", fontsize=8.5, color=TINTA_2)
        ax.text(100 * r.custo_giro + 0.2, i - h / 2, f"{100 * r.custo_giro:.1f}%".replace(".", ","),
                va="center", fontsize=8.5, color=TINTA_2)
    ax.set_yticks(list(y), [f"{s} ({n})" for s, n in zip(df.segmento, df.empresas)])
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("% da receita líquida (mediana do segmento)")
    ax.legend(loc="lower right", frameon=False, fontsize=8.5)
    _titulo(fig, f"Quanto do lucro operacional o capital de giro consome ({ano})",
            f"Custo = (estoques + contas a receber − fornecedores) × Selic média de "
            f"{selic:.1f}% ÷ receita. Entre parênteses, nº de empresas.".replace(".", ",", 1))
    _fonte(fig)
    arq = pasta / "custo_do_giro.png"
    fig.savefig(arq, dpi=150)
    plt.close(fig)
    return arq


def gerar_todos(con: duckdb.DuckDBPyConnection, pasta: Path) -> list[Path]:
    pasta.mkdir(exist_ok=True)
    return [ciclo_por_empresa(con, pasta), selic_e_prazos(con, pasta), custo_do_giro(con, pasta)]
