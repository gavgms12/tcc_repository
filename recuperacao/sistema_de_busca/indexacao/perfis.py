
from recuperacao.sistema_de_busca.textos import gerar_hash


# alterar para novo dado
def _ano(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def criar_perfis(registros, montar_texto, id_campo, montar_metadata, mapa_professores=None):
    perfis = []
    for r in registros:
        texto = montar_texto(r)
        if not texto:
            continue

        metadata = montar_metadata(r)
        if mapa_professores is not None:
            metadata["professor_ids"] = sorted(mapa_professores.get(str(r[id_campo]), []))

        perfis.append({
            "id": r[id_campo],
            "texto": texto,
            "metadata": metadata,
            "hash": gerar_hash({"texto": texto, "metadata": metadata}),
        })
    return perfis