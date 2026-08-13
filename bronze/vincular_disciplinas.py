#!/usr/bin/env python3
"""Vincula professores às disciplinas e enriquece o cadastro mesclado."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from scrape_sigaa_componentes import extrair_detalhe_componente
from sigaa_utils import buscar_html, criar_sessao, url_absoluta

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DOCENTES = ROOT_DIR / "data" / "bronze" / "sigaa" / "docentes.json"
DEFAULT_COMPONENTES = ROOT_DIR / "data" / "bronze" / "sigaa" / "componentes.json"
DEFAULT_MERGED = ROOT_DIR / "data" / "bronze" / "merged" / "professores.json"
DEFAULT_VINCULOS = ROOT_DIR / "data" / "bronze" / "sigaa" / "vinculos_professor_disciplina.json"


def carregar_json(caminho: Path) -> dict | list:
    with caminho.open(encoding="utf-8") as arquivo:
        return json.load(arquivo)


def indice_componentes(componentes_payload: dict) -> dict[str, dict]:
    indice: dict[str, dict] = {}
    for componente in componentes_payload.get("componentes", []):
        id_sigaa = componente.get("idSigaa")
        if id_sigaa:
            indice[id_sigaa] = componente
    return indice


def ids_disciplinas_vinculadas(docentes_payload: dict) -> set[str]:
    ids: set[str] = set()
    for docente in docentes_payload.get("docentes", []):
        for disciplina in docente.get("disciplinasMinistradas", []):
            id_sigaa = disciplina.get("idSigaa")
            if id_sigaa:
                ids.add(id_sigaa)
    return ids


def enriquecer_ementas_vinculadas(
    componentes_payload: dict,
    ids_vinculados: set[str],
    *,
    pausa: float = 0.25,
) -> None:
    if not ids_vinculados:
        return

    import time

    session = criar_sessao()
    componentes = componentes_payload.get("componentes", [])
    por_id = {item["idSigaa"]: item for item in componentes if item.get("idSigaa")}

    faltantes = [
        id_sigaa for id_sigaa in ids_vinculados if not por_id.get(id_sigaa, {}).get("ementa")
    ]
    if not faltantes:
        return

    buscar_html(
        session,
        "https://sigaa.unifei.edu.br/sigaa/public/departamento/componentes.jsf?id=127",
        pausa=0,
    )

    print(f"Buscando ementa de {len(faltantes)} componentes vinculados...")

    for indice, id_sigaa in enumerate(sorted(faltantes)):
        if indice > 0 and pausa > 0:
            time.sleep(pausa)

        if (indice + 1) % 25 == 0 or indice == 0:
            print(f"  [{indice + 1}/{len(faltantes)}] idSigaa={id_sigaa}")

        url = url_absoluta(f"/sigaa/link/public/ensino/visualizarComponente/{id_sigaa}")
        detalhe = extrair_detalhe_componente(buscar_html(session, url))
        if id_sigaa in por_id and detalhe.get("ementa"):
            por_id[id_sigaa]["ementa"] = detalhe["ementa"]
            if detalhe.get("tipo"):
                por_id[id_sigaa]["tipo"] = detalhe["tipo"]


def disciplinas_unicas(registros: list[dict]) -> list[dict]:
    vistos: set[tuple[str | None, str | None]] = set()
    unicas: list[dict] = []

    for registro in registros:
        chave = (registro.get("idSigaa"), registro.get("codigo"))
        if chave in vistos:
            continue
        vistos.add(chave)
        unicas.append(registro)

    return unicas


def montar_vinculos(docentes_payload: dict, componentes_por_id: dict[str, dict]) -> list[dict]:
    vinculos: list[dict] = []

    for docente in docentes_payload.get("docentes", []):
        disciplinas = disciplinas_unicas(docente.get("disciplinasMinistradas", []))
        disciplinas_enriquecidas = []

        for disciplina in disciplinas:
            id_sigaa = disciplina.get("idSigaa")
            catalogo = componentes_por_id.get(id_sigaa, {}) if id_sigaa else {}
            disciplinas_enriquecidas.append(
                {
                    "idSigaa": id_sigaa,
                    "codigo": disciplina.get("codigo") or catalogo.get("codigo"),
                    "nome": disciplina.get("nome") or catalogo.get("nome"),
                    "cargaHoraria": disciplina.get("cargaHoraria") or catalogo.get("cargaHoraria"),
                    "ementa": catalogo.get("ementa"),
                    "periodos": sorted(
                        {
                            item.get("periodo")
                            for item in docente.get("disciplinasMinistradas", [])
                            if item.get("idSigaa") == id_sigaa
                            or item.get("codigo") == disciplina.get("codigo")
                        }
                        - {None}
                    ),
                }
            )

        vinculos.append(
            {
                "siape": docente.get("siape"),
                "nome": docente.get("nome"),
                "disciplinas": disciplinas_enriquecidas,
            }
        )

    return vinculos


def enriquecer_merged(
    merged: list[dict],
    docentes_payload: dict,
    vinculos: list[dict],
) -> list[dict]:
    docentes_por_siape = {doc["siape"]: doc for doc in docentes_payload.get("docentes", [])}
    vinculos_por_siape = {item["siape"]: item for item in vinculos}

    for professor in merged:
        siape = professor.get("siape")
        if not siape:
            continue

        docente = docentes_por_siape.get(siape, {})
        vinculo = vinculos_por_siape.get(siape, {})

        professor["disciplinasSigaa"] = [
            {
                "codigo": disciplina.get("codigo"),
                "nome": disciplina.get("nome"),
                "idSigaa": disciplina.get("idSigaa"),
            }
            for disciplina in vinculo.get("disciplinas", [])
        ]
        professor["sigaa"] = {
            "perfil": docente.get("perfil", {}),
            "contatos": docente.get("contatos", {}),
            "producaoIntelectual": docente.get("producaoIntelectual", []),
            "projetosPesquisa": docente.get("projetosPesquisa", []),
        }

    return merged


def salvar_json(dados: dict | list, caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)
        arquivo.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Vincula professores às disciplinas e enriquece o JSON mesclado."
    )
    parser.add_argument("--docentes", type=Path, default=DEFAULT_DOCENTES)
    parser.add_argument("--componentes", type=Path, default=DEFAULT_COMPONENTES)
    parser.add_argument("--merged", type=Path, default=DEFAULT_MERGED)
    parser.add_argument("--vinculos-output", type=Path, default=DEFAULT_VINCULOS)
    parser.add_argument(
        "--sem-merged",
        action="store_true",
        help="Não atualiza o arquivo merged/professores.json.",
    )
    parser.add_argument(
        "--buscar-ementa-vinculadas",
        action="store_true",
        help="Busca ementa apenas das disciplinas ministradas pelos docentes.",
    )
    args = parser.parse_args()

    if not args.docentes.exists():
        raise FileNotFoundError(f"Arquivo de docentes não encontrado: {args.docentes}")

    docentes_payload = carregar_json(args.docentes)
    componentes_payload = (
        carregar_json(args.componentes) if args.componentes.exists() else {"componentes": []}
    )

    if args.buscar_ementa_vinculadas:
        ids_vinculados = ids_disciplinas_vinculadas(docentes_payload)
        enriquecer_ementas_vinculadas(componentes_payload, ids_vinculados)
        salvar_json(componentes_payload, args.componentes)

    componentes_por_id = indice_componentes(componentes_payload)
    vinculos = montar_vinculos(docentes_payload, componentes_por_id)

    payload_vinculos = {
        "coletadoEm": datetime.now(timezone.utc).isoformat(),
        "total": len(vinculos),
        "vinculos": vinculos,
    }
    salvar_json(payload_vinculos, args.vinculos_output)

    if not args.sem_merged and args.merged.exists():
        merged = carregar_json(args.merged)
        enriquecer_merged(merged, docentes_payload, vinculos)
        salvar_json(merged, args.merged)
        print(f"Cadastro mesclado enriquecido em: {args.merged}")

    total_disciplinas = sum(len(item["disciplinas"]) for item in vinculos)
    print(f"Vínculos gerados: {len(vinculos)} professores, {total_disciplinas} disciplinas únicas.")
    print(f"Arquivo salvo em: {args.vinculos_output}")


if __name__ == "__main__":
    main()
