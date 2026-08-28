import re
import unicodedata
import json 
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_LATTES = ROOT_DIR / "data" / "silver" / "docentes"
DEFAULT_INPUT_SITE_CANDIDATES = [
    ROOT_DIR / "data" / "bronze" / "merged" / "professores_sigaa_iesti_merged.json",
    ROOT_DIR / "data" / "bronze" / "merged" / "professores.json",
]
DEFAULT_OUTPUT = ROOT_DIR / "data" / "silver" / "professores_unificados.json"


def resolver_input_site() -> Path:
    for caminho in DEFAULT_INPUT_SITE_CANDIDATES:
        if caminho.exists():
            return caminho
    raise FileNotFoundError(
        "Arquivo mesclado da Bronze não encontrado. Esperado um de: "
        + ", ".join(str(c) for c in DEFAULT_INPUT_SITE_CANDIDATES)
    )

def normalizar_titulo(titulo):
    titulo = re.sub(r'^[A-Z]{2,6}-?\d{2,6}-\d{2,4}\s*-\s*', '', titulo)
    titulo = re.sub(r'<[^>]+>', '', titulo)
    titulo = unicodedata.normalize('NFKD', titulo).encode('ASCII', 'ignore').decode()
    titulo = re.sub(r'[^a-zA-Z0-9 ]', '', titulo).lower()
    return re.sub(r'\s+', ' ', titulo).strip()

from collections import defaultdict

def extrair_tcc_site(item_texto):
    #'Trabalho de Fim de Curso': titulo, aluno , mes/ano
    partes = item_texto.split(' , ')
    if len(partes) < 2:
        return None
    titulo_aluno = ' , '.join(partes[:-1])
    data = partes[-1].strip()
    if ',' in titulo_aluno:
        titulo, aluno = titulo_aluno.rsplit(',', 1)
    else:
        titulo, aluno = titulo_aluno, ''
    return {'titulo': titulo.strip(), 'aluno': aluno.strip(), 'data': data}

# regulariza tccs duplicados por aluno
def unir_tccs(prof_site, prof_lattes):
    orientacoes = prof_lattes.get('orientacoes', [])
    tccs_lattes = [o for o in orientacoes if o.get('tipo') == 'tcc']

    categorias = prof_site.get('sigaa', {}).get('producaoIntelectual', [])
    tcc_itens = next((c['itens'] for c in categorias if c['categoria'] == 'Trabalho de Fim de Curso'), [])

    site_por_titulo = defaultdict(list)
    for item_texto in tcc_itens:
        extraido = extrair_tcc_site(item_texto)
        if extraido:
            chave = normalizar_titulo(extraido['titulo'])
            site_por_titulo[chave].append(extraido)

    resultado = []
    titulos_usados = set()

    for tcc in tccs_lattes:
        chave = normalizar_titulo(tcc['titulo'])
        item = dict(tcc)
        if chave in site_por_titulo:
            titulos_usados.add(chave)
        resultado.append(item)

    # adiciona TCCs que só existem no site
    for chave, entradas in site_por_titulo.items():
        if chave in titulos_usados:
            continue
        
        resultado.append({
            'titulo': entradas[0]['titulo'],
            #'alunos': [e['aluno'] for e in entradas],
            'data': entradas[0]['data'],
            'fonte': 'site',
        })

    return resultado

def extrair_artigo_site(item_texto):
    # Categoria 'Artigos': ano, autores , titulo , ISSN: xxxx
    partes = item_texto.split(' , ')
    if len(partes) < 3:
        return None
    autores = re.sub(r'^\d{4},\s*', '', partes[0]).strip()
    titulo = partes[1].strip()
    issn = partes[2].replace('ISSN:', '').strip()
    return {'autores': autores, 'titulo': titulo, 'issn': issn}


def extrair_evento_site(item_texto, titulo_lattes=None):
    #'Publicação em Eventos': ano, autores, titulo , veiculo, status
    partes = item_texto.split(' , ')
    if len(partes) < 2:
        return None
    autores_titulo = re.sub(r'^\d{4},\s*', '', partes[0]).strip()
    resto = ' , '.join(partes[1:])

    autores, titulo = None, None
    if titulo_lattes:
        match = re.search(re.escape(titulo_lattes), autores_titulo, re.IGNORECASE)
        if match:
            autores = autores_titulo[:match.start()].rstrip(', ').strip()
            titulo = autores_titulo[match.start():match.end()]

    return {'autores': autores, 'titulo': titulo, 'venue_status': resto}

def extrair_capitulo_site(item_texto, titulo_lattes=None):
    # Categoria 'Capítulos de Livros': ano, titulo_capitulo, titulo_livro, autor1, autor2, ...

    texto_sem_ano = re.sub(r'^\d{4},\s*', '', item_texto)
    titulo, complemento = None, None
    if titulo_lattes:
        titulo_capitulo = titulo_lattes.split('. ')[0]
        match = re.search(re.escape(titulo_capitulo), texto_sem_ano, re.IGNORECASE)
        if match:
            titulo = texto_sem_ano[match.start():match.end()]
            complemento = texto_sem_ano[match.end():].lstrip(', ').strip()
    return {'titulo': titulo, 'complemento': complemento}
 
CATEGORIA_PARA_TIPOS = {
    'Artigos': ['artigo_periodico'],
    'Publicação em Eventos': ['trabalho_congresso', 'resumo_congresso', 'apresentacao_trabalho'],
    'Capítulos de Livros': ['capitulo_livro'],
}
 
CATEGORIAS_TITULO_PARCIAL = {'Capítulos de Livros'}

def unir_producoes(prof_site, prof_lattes, ids_ignorar=None):
    ids_ignorar = ids_ignorar or set()
    vistos_ids = set()
    producoes_lattes = []
    for p in prof_lattes.get('producoes', []):
        if p.get('id') in vistos_ids or p.get('id') in ids_ignorar:
            continue
        vistos_ids.add(p.get('id'))
        producoes_lattes.append(p)

    producao_site_por_categoria = {
        c['categoria']: c['itens']
        for c in prof_site.get('sigaa', {}).get('producaoIntelectual', [])
    }
    resultado_por_tipo = {}
    itens_site_usados = {cat: set() for cat in CATEGORIA_PARA_TIPOS}
 
    for prod in producoes_lattes:
        tipo = prod.get('tipo')
        item = dict(prod)
 
        categoria_site = next((c for c, tipos in CATEGORIA_PARA_TIPOS.items() if tipo in tipos), None)
        if categoria_site:
            
            titulo_para_comparar = prod['titulo']
            if categoria_site in CATEGORIAS_TITULO_PARCIAL:
                titulo_para_comparar = titulo_para_comparar.split('. ')[0]
            titulo_norm = normalizar_titulo(titulo_para_comparar)
 
            itens_categoria = producao_site_por_categoria.get(categoria_site, [])
 
            for idx, item_texto in enumerate(itens_categoria):
                if idx in itens_site_usados[categoria_site]:
                    continue
 
                if categoria_site == 'Artigos':
                    extraido = extrair_artigo_site(item_texto)
                    if extraido and normalizar_titulo(extraido['titulo']) == titulo_norm:
                        item['autores'] = extraido['autores']
                        item.setdefault('issn', extraido['issn'])
                        itens_site_usados[categoria_site].add(idx)
                        break
                elif categoria_site == 'Publicação em Eventos':
                    if titulo_norm in normalizar_titulo(item_texto):
                        extraido = extrair_evento_site(item_texto, titulo_lattes=titulo_para_comparar)
                        if extraido:
                            item['autores'] = extraido['autores']
                        itens_site_usados[categoria_site].add(idx)
                        break
                elif categoria_site == 'Capítulos de Livros':
                    if titulo_norm in normalizar_titulo(item_texto):
                        extraido = extrair_capitulo_site(item_texto, titulo_lattes=titulo_para_comparar)
                        if extraido:
                            item['informacoes_complementares'] = extraido['complemento']
                        itens_site_usados[categoria_site].add(idx)
                        break
 
        resultado_por_tipo.setdefault(tipo, []).append(item)
 
    # itens do site sem correspondência no Lattes -> adiciona mesmo assim
    for categoria_site, tipos in CATEGORIA_PARA_TIPOS.items():
        tipo_padrao = tipos[0]
        itens_categoria = producao_site_por_categoria.get(categoria_site, [])
        for idx, item_texto in enumerate(itens_categoria):
            if idx in itens_site_usados[categoria_site]:
                continue
 
            if categoria_site == 'Artigos':
                extraido = extrair_artigo_site(item_texto)
                if extraido:
                    resultado_por_tipo.setdefault(tipo_padrao, []).append({
                        'titulo': extraido['titulo'],
                        'autores': extraido['autores'],
                        'issn': extraido['issn'],
                        'fonte': 'site',
                    })
            elif categoria_site == 'Publicação em Eventos':
                extraido = extrair_evento_site(item_texto)
                resultado_por_tipo.setdefault(tipo_padrao, []).append({
                    'titulo': item_texto,
                    'venue_status': extraido['venue_status'] if extraido else None,
                    'fonte': 'site',
                })
            elif categoria_site == 'Capítulos de Livros':
                resultado_por_tipo.setdefault(tipo_padrao, []).append({
                    'titulo': re.sub(r'^\d{4},\s*', '', item_texto),
                    'fonte': 'site',
                })
 
    return resultado_por_tipo

def unir_iniciacao_cientifica(prof_site, prof_lattes):
    """Cruza IC do Lattes (orientacoes com tipo='iniciacao_cientifica') com IC do site
    (trabalhosIniciacaoCientifica) e com resumo_expandido do Lattes de mesmo título, sem duplicar."""
    orientacoes_lattes = prof_lattes.get('orientacoes', [])
    ics_site = prof_site.get('trabalhosIniciacaoCientifica', [])
    producoes_lattes = prof_lattes.get('producoes', [])

    ics_lattes = [o for o in orientacoes_lattes if o.get('tipo') == 'iniciacao_cientifica']
    index_site = {normalizar_titulo(ic['titulo']): ic for ic in ics_site}

    resumos_expandidos = {
        normalizar_titulo(p['titulo']): p
        for p in producoes_lattes
        if p.get('tipo') == 'resumo_expandido'
    }

    resultado = []
    titulos_usados_site = set()
    ids_absorvidos = set()

    for ic in ics_lattes:
        chave = normalizar_titulo(ic['titulo'])
        par_site = index_site.get(chave)
        par_resumo = resumos_expandidos.get(chave)

        item = {
            'titulo': ic['titulo'],
            #'orientando': ic.get('orientando'),
            'ano_inicio': ic.get('ano_inicio'),
            #'status': ic.get('status'),
        }

        if par_site:
            item['autores'] = par_site.get('autores')
            item['resumo'] = par_site.get('resumo')
            item['palavrasChaves'] = par_site.get('palavrasChaves', [])
            item['ano_site'] = par_site.get('ano')
            titulos_usados_site.add(chave)

        if par_resumo:
            item['resumo_expandido'] = {
                'id': par_resumo.get('id'),
                'ano': par_resumo.get('ano'),
                'veiculo': par_resumo.get('veiculo'),
                'doi': par_resumo.get('doi'),
            }
            ids_absorvidos.add(par_resumo.get('id'))

        resultado.append(item)

    for chave, ic in index_site.items():
        if chave not in titulos_usados_site:
            resultado.append({
                'titulo': ic['titulo'],
                #'autores': ic.get('autores'),
                'palavrasChaves': ic.get('palavrasChaves', []),
                'ano': ic.get('ano'),
                'resumo': ic.get('resumo')
            })

    return resultado, ids_absorvidos

def unir_professor(prof_site, prof_lattes):
    docente_lattes = prof_lattes['docente']
    orientacoes = prof_lattes.get('orientacoes', [])
    orientacoes_sem_ic_nem_tcc = [
        ori for ori in orientacoes if ori.get('tipo') not in ('iniciacao_cientifica', 'tcc')
    ]

    iniciacao_cientifica, ids_resumo_absorvidos = unir_iniciacao_cientifica(prof_site, prof_lattes)

    unificado = {
        'idLattes': prof_site['idLattes'],
        'nome': docente_lattes.get('nome', prof_site.get('nome')),
        'siape': prof_site.get('siape'),
        'unidade': docente_lattes.get('unidade'),
        'resumo': docente_lattes.get('resumo'),
        'disciplinasSigaa': prof_site.get('disciplinasSigaa', []),
        'competencias': prof_lattes.get('competencias', {}),
        'producoes': unir_producoes(prof_site, prof_lattes, ids_ignorar=ids_resumo_absorvidos),
        'orientacoes': orientacoes_sem_ic_nem_tcc,
        'tccs': unir_tccs(prof_site, prof_lattes),
        'projetos': prof_lattes.get('projetos', []),
        'iniciacaoCientifica': iniciacao_cientifica,
    }

    return unificado

resultado = []
# ver se resumo expandido ok em relação a ser considerado tambem ic

# --- Carregar os dois arquivos ---
DEFAULT_INPUT_SITE = resolver_input_site()
with open(DEFAULT_INPUT_SITE, 'r', encoding='utf-8') as f:
    dados_site = json.load(f)

for item in DEFAULT_INPUT_LATTES.iterdir(): 
    with open(item, 'r', encoding='utf-8') as f:
        dados_lattes = json.load(f)
        
# ligar os professores por meio do id lattes que está no nome do arquivo com o que está no json 
# --- Indexar por idLattes para fazer o merge ---

    arquivo_lattes = item.name
    index_lattes = re.sub(r'\.\w+$',"", arquivo_lattes)

    # otimizar já que o json do lattes está em ordem crescente
    for prof_site in dados_site:
        chave = prof_site['idLattes']
        if index_lattes == chave:
            resultado.append(unir_professor(prof_site, dados_lattes))
            break
        

with open(DEFAULT_OUTPUT, 'w', encoding='utf-8') as f:
    json.dump(resultado, f, ensure_ascii=False, indent=2)
    
    