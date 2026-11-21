"""Extração: baixa os dados públicos da CVM e do Banco Central, com cache local.

- CVM: Demonstrações Financeiras Padronizadas (DFP), um .zip por ano, em
  https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/
- BCB: séries do Sistema Gerenciador de Séries Temporais (SGS), via API pública.

Os arquivos baixados ficam em dados/brutos/ e não são baixados de novo.
"""
from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path

import requests

URL_DFP = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/dfp_cia_aberta_{ano}.zip"
URL_SGS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados?formato=json&dataInicial={ini}&dataFinal={fim}"

# Só as demonstrações consolidadas que o projeto usa.
DEMONSTRACOES = ("DRE_con", "BPA_con", "BPP_con")

SERIES_BCB = {
    433: "ipca_mensal",     # IPCA, variação % no mês
    4189: "selic_anual",    # Selic acumulada no mês, anualizada (base 252), % a.a.
}

CABECALHO = {"User-Agent": "benchmark-varejo-cvm (projeto de estudo)"}


def _baixar(url: str, destino: Path, tentativas: int = 3) -> None:
    for t in range(1, tentativas + 1):
        try:
            with requests.get(url, headers=CABECALHO, timeout=120, stream=True) as r:
                r.raise_for_status()
                tmp = destino.with_suffix(destino.suffix + ".parcial")
                with open(tmp, "wb") as f:
                    for bloco in r.iter_content(1 << 20):
                        f.write(bloco)
                tmp.replace(destino)
                return
        except requests.RequestException:
            if t == tentativas:
                raise
            time.sleep(3 * t)


def baixar_dfp(ano: int, pasta: Path) -> list[Path]:
    """Baixa a DFP de um ano e extrai as demonstrações usadas. Devolve os CSVs."""
    pasta.mkdir(parents=True, exist_ok=True)
    zip_ = pasta / f"dfp_cia_aberta_{ano}.zip"
    if not zip_.exists():
        _baixar(URL_DFP.format(ano=ano), zip_)
    csvs = []
    with zipfile.ZipFile(zip_) as z:
        for dem in DEMONSTRACOES:
            nome = f"dfp_cia_aberta_{dem}_{ano}.csv"
            alvo = pasta / nome
            if not alvo.exists():
                z.extract(nome, pasta)
            csvs.append(alvo)
    return csvs


def baixar_bcb(pasta: Path, ano_ini: int, ano_fim: int) -> dict[str, Path]:
    """Baixa as séries do BCB em JSON. Devolve {nome: arquivo}."""
    pasta.mkdir(parents=True, exist_ok=True)
    saida = {}
    for serie, nome in SERIES_BCB.items():
        alvo = pasta / f"{nome}_{ano_ini}_{ano_fim}.json"
        if not alvo.exists():
            url = URL_SGS.format(serie=serie, ini=f"01/01/{ano_ini}", fim=f"31/12/{ano_fim}")
            r = requests.get(url, headers=CABECALHO, timeout=60)
            r.raise_for_status()
            dados = r.json()
            if not dados:
                raise ValueError(f"Série {serie} veio vazia")
            alvo.write_text(json.dumps(dados), encoding="utf-8")
        saida[nome] = alvo
    return saida
