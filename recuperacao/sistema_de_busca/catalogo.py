"""Catálogo de tópicos (o mesmo de GET /topicos) e geração do arquivo estático do front.

O front lê recuperacao/frontend/topicos.json primeiro: os temas aparecem na hora, sem esperar a API
(no Modal, um cold start da GPU leva ~30-60 s). Gerado automaticamente no `modal deploy` e no
workflow do GitHub Pages; para atualizar à mão depois de mudar TOPICOS em config.py:
    python -m recuperacao.sistema_de_busca.catalogo
"""
import json
from pathlib import Path

from recuperacao.sistema_de_busca import config

ARQUIVO_FRONT = Path(__file__).resolve().parents[1] / "frontend" / "topicos.json"


def catalogo_topicos() -> dict:
    detalhes = [
        {
            "nome": nome,
            "categoria": (dados.get("categoria") if isinstance(dados, dict) else None) or "Outros",
            "descricao": dados.get("descricao") if isinstance(dados, dict) else dados,
            "disciplinas": config.disciplinas_topico(nome),
        }
        for nome, dados in config.TOPICOS.items()
    ]
    return {"topicos": list(config.TOPICOS), "detalhes": detalhes}


def gerar_arquivo(caminho: Path = ARQUIVO_FRONT) -> Path:
    caminho.write_text(json.dumps(catalogo_topicos(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return caminho


if __name__ == "__main__":
    print(f"Catálogo salvo em {gerar_arquivo()}")
