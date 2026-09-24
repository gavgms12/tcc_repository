#!/usr/bin/env python3
"""Extrai título e ano de itens de produção docente via IA (Hugging Face).

Usa a camada gratuita da Hugging Face Inference API com um modelo aberto para
separar o título de um trabalho do restante da citação (autores, veículo,
paginação). Se o token não estiver configurado ou a chamada falhar por
qualquer motivo (rede, rate limit, resposta fora do formato esperado), cai
para uma heurística por regex — a limpeza da Silver não pode travar por causa
de uma dependência externa.
"""

from __future__ import annotations

import json
import os
import re

ANO_RE = re.compile(r"\b(?:19|20)\d{2}\b")
TITULO_RE = re.compile(r"^[^.]*\.\s*(?P<titulo>[^.]+)\.")
BLOCO_JSON_RE = re.compile(r"\[.*\]", re.DOTALL)

DEFAULT_MODELO = "Qwen/Qwen2.5-7B-Instruct"

_aviso_token_emitido = False


def _extrair_por_regex(item: str) -> dict:
    anos = ANO_RE.findall(item)
    ano = int(anos[-1]) if anos else None

    match = TITULO_RE.match(item)
    titulo = match.group("titulo").strip() if match else item.strip()

    return {"titulo": titulo, "ano": ano}


def _fallback(itens: list[str]) -> list[dict]:
    return [_extrair_por_regex(item) for item in itens]


def _montar_prompt(itens: list[str]) -> str:
    lista = "\n".join(f"{indice + 1}. {item}" for indice, item in enumerate(itens))
    return (
        "Você recebe uma lista numerada de citações de produção acadêmica de um "
        "docente, no formato bruto extraído do SIGAA (pode conter autores, "
        "alunos/coautores, veículo de publicação, volume e ano).\n\n"
        "Para cada item, devolva apenas o título do trabalho (sem nomes de "
        "autores, alunos ou participantes) e o ano de publicação, se houver.\n\n"
        "Responda SOMENTE com um array JSON, na mesma ordem e com o mesmo "
        "tamanho da lista de entrada, no formato: "
        '[{"titulo": "...", "ano": 2020}, {"titulo": "...", "ano": null}]\n\n'
        f"Lista:\n{lista}"
    )


def _chamar_huggingface(itens: list[str], modelo: str, token: str) -> list[dict]:
    from huggingface_hub import InferenceClient

    cliente = InferenceClient(model=modelo, token=token)
    resposta = cliente.chat_completion(
        messages=[{"role": "user", "content": _montar_prompt(itens)}],
        max_tokens=1024,
        temperature=0.0,
    )
    texto = resposta.choices[0].message.content or ""

    bloco = BLOCO_JSON_RE.search(texto)
    if not bloco:
        raise ValueError("Resposta da IA não contém um array JSON.")

    dados = json.loads(bloco.group(0))
    if not isinstance(dados, list) or len(dados) != len(itens):
        raise ValueError("Resposta da IA com formato ou tamanho inesperado.")

    resultado = []
    for entrada in dados:
        titulo = str(entrada.get("titulo") or "").strip()
        ano = entrada.get("ano")
        ano = int(ano) if isinstance(ano, (int, str)) and str(ano).strip().isdigit() else None
        resultado.append({"titulo": titulo, "ano": ano})

    return resultado


def extrair_titulos(itens: list[str]) -> list[dict]:
    """Extrai {"titulo", "ano"} de cada item bruto, na mesma ordem de entrada."""
    global _aviso_token_emitido

    if not itens:
        return []

    token = os.getenv("HF_TOKEN")
    if not token:
        if not _aviso_token_emitido:
            print("AVISO: HF_TOKEN não configurado; usando extração de títulos por regex.")
            _aviso_token_emitido = True
        return _fallback(itens)

    modelo = os.getenv("HF_MODELO_TITULOS", DEFAULT_MODELO)
    try:
        return _chamar_huggingface(itens, modelo, token)
    except Exception as erro:  # noqa: BLE001 - qualquer falha da IA cai no fallback
        print(f"AVISO: extração de títulos via Hugging Face falhou ({erro}); usando regex.")
        return _fallback(itens)
