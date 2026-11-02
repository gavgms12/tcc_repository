#!/usr/bin/env python3
"""Inspeciona um Parquet da camada Silver para conferência manual.

Lê a chave informada do bucket `silver` no MinIO e imprime: schema (colunas),
total de registros, uma amostra legível (JSON indentado) e um resumo de
preenchimento por campo (quantos registros vieram vazios/nulos) — útil para
pegar de olho se algum campo saiu sistematicamente vazio por um bug de
scraping/limpeza.

Exemplos:
    python silver/inspecionar_parquet.py perfis_sigaa_limpos.parquet
    python silver/inspecionar_parquet.py perfis_lattes_limpos.parquet --amostra 3
    python silver/inspecionar_parquet.py perfis_lattes_limpos.parquet --idlattes 3709633136002980
    python silver/inspecionar_parquet.py componentes_curriculares.parquet --exportar saida.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from storage.minio_storage import ler_parquet_silver

ARQUIVOS_CONHECIDOS = [
    "professores_unificados.parquet",
    "perfis_sigaa_limpos.parquet",
    "perfis_lattes_limpos.parquet",
    "componentes_curriculares.parquet",
    "componentes_curriculares_externos.parquet",
    "trabalhos_ic_periodicos.parquet",
]


def vazio(valor: Any) -> bool:
    """Considera vazio: None, string em branco, lista/dict vazios."""
    if valor is None:
        return True
    if isinstance(valor, str):
        return not valor.strip()
    if isinstance(valor, (list, dict)):
        return len(valor) == 0
    return False


def resumo_preenchimento(registros: list[dict]) -> list[tuple[str, int, int]]:
    """Para cada campo: (nome, quantos preenchidos, quantos vazios)."""
    colunas: list[str] = []
    for registro in registros:
        for chave in registro:
            if chave not in colunas:
                colunas.append(chave)

    resumo = []
    for coluna in colunas:
        vazios = sum(1 for r in registros if vazio(r.get(coluna)))
        resumo.append((coluna, len(registros) - vazios, vazios))
    return resumo


def imprimir_resumo(chave: str, registros: list[dict]) -> None:
    print(f"\n=== {chave} ===")
    print(f"Total de registros: {len(registros)}")

    if not registros:
        print("(vazio)")
        return

    print("\nPreenchimento por campo (preenchidos / vazios):")
    for coluna, preenchidos, vazios in resumo_preenchimento(registros):
        marca = "  <-- todos vazios!" if preenchidos == 0 else ""
        print(f"  {coluna:35s} {preenchidos:4d} / {vazios:<4d}{marca}")


def imprimir_amostra(registros: list[dict], quantidade: int) -> None:
    if not registros or quantidade <= 0:
        return
    print(f"\nAmostra ({min(quantidade, len(registros))} de {len(registros)} registros):")
    for registro in registros[:quantidade]:
        print(json.dumps(registro, ensure_ascii=False, indent=2, default=str))
        print("-" * 60)


def buscar_por_identificador(
    registros: list[dict], nome: str | None, id_lattes: str | None, siape: str | None
) -> list[dict]:
    filtrados = registros
    if nome:
        alvo = nome.strip().lower()
        filtrados = [r for r in filtrados if alvo in str(r.get("nome", "")).lower()]
    if id_lattes:
        filtrados = [r for r in filtrados if str(r.get("idLattes")) == id_lattes]
    if siape:
        filtrados = [r for r in filtrados if str(r.get("siape")) == siape]
    return filtrados


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspeciona um Parquet da Silver (MinIO) para conferência manual."
    )
    parser.add_argument(
        "chave",
        nargs="?",
        help=(
            "Nome do arquivo no bucket silver (ex.: perfis_lattes_limpos.parquet). "
            "Sem argumento, lista os arquivos conhecidos e sai."
        ),
    )
    parser.add_argument(
        "--amostra",
        type=int,
        default=2,
        help="Quantos registros completos imprimir como amostra (padrão: 2).",
    )
    parser.add_argument("--nome", help="Filtra registros cujo nome contenha este texto.")
    parser.add_argument("--idlattes", help="Filtra pelo idLattes exato.")
    parser.add_argument("--siape", help="Filtra pelo siape exato.")
    parser.add_argument(
        "--exportar",
        help="Exporta todos os registros (já filtrados) como JSON legível neste caminho local.",
    )
    args = parser.parse_args()

    if not args.chave:
        print("Informe o arquivo a inspecionar. Arquivos conhecidos da Silver:")
        for nome_arquivo in ARQUIVOS_CONHECIDOS:
            print(f"  - {nome_arquivo}")
        return

    registros = ler_parquet_silver(args.chave)

    if args.nome or args.idlattes or args.siape:
        registros = buscar_por_identificador(registros, args.nome, args.idlattes, args.siape)
        print(f"Filtro aplicado: {len(registros)} registro(s) encontrado(s).")

    imprimir_resumo(args.chave, registros)
    imprimir_amostra(registros, args.amostra)

    if args.exportar:
        caminho = Path(args.exportar)
        caminho.write_text(
            json.dumps(registros, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"\nExportado para: {caminho.resolve()}")


if __name__ == "__main__":
    main()
