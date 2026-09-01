import re
import unicodedata
import json 
from pathlib import Path
from datetime import datetime

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_LATTES = ROOT_DIR / "data" / "silver" / "docentes"
DEFAULT_INPUT_SITE_CANDIDATES = [
    ROOT_DIR / "data" / "bronze" / "merged" / "professores_sigaa_iesti_merged.json",
    ROOT_DIR / "data" / "bronze" / "merged" / "professores.json",
]
DEFAULT_OUTPUT = ROOT_DIR / "data" / "silver" / "professores_unificados.json"

ano_limite = datetime.now().year - 10

def obter_categoria(prof_site, nome_categoria):
    resultado = []

    for item in prof_site.get("sigaa").get('producaoIntelectual', []):
        if item.get('categoria') == nome_categoria:
            resultado = item.get('itens', [])
            break
    return normalizar_banca(resultado)
    
    
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
    ano = re.sub(r'^\d{2}\/','', data)
    if ',' in titulo_aluno:
        titulo, aluno = titulo_aluno.rsplit(',', 1)
    else:
        titulo, aluno = titulo_aluno, ''
    return {'titulo': titulo.strip(), 'aluno': aluno.strip(), 'ano': int(ano)}

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
        resultado.append({
            'titulo': item['titulo'],
            'ano' : item['ano_inicio']
        })

    # adiciona TCCs que só existem no site
    for chave, entradas in site_por_titulo.items():
        if chave in titulos_usados:
            continue
        ano = entradas[0]['ano']
        if ano > ano_limite:
            resultado.append({
                'titulo': entradas[0]['titulo'],
                #'alunos': [e['aluno'] for e in entradas],
                'ano': entradas[0]['ano']
            })

    return resultado

def extrair_artigo_site(item_texto):
    # Categoria 'Artigos': ano, autores , titulo , ISSN: xxxx
    partes = item_texto.split(' , ')
    if len(partes) < 3:
        return None
    
    ano = partes[0].split(',', 1)[0].strip()
    autores = re.sub(r'^\d{4},\s*', '', partes[0]).strip()
    titulo = partes[1].strip()
    issn = partes[2].replace('ISSN:', '').strip()
    return {'autores': autores, 'titulo': titulo, 'issn': issn, 'ano': int(ano)}

def normalizar_banca(bancas_site):
    # Categoria 'Participações em Bancas de Cursos': ano, titulo, defensor
    bancas = []
    for banca_crua in bancas_site:
        partes = banca_crua.split(', ')
        if len(partes) < 2:
            return None
        
        ano = int(partes[0].strip())
        titulo = partes[1].strip()
        defensor = partes[2].strip()
        banca_normalizada ={'titulo': titulo, 'ano' : ano}
        
        titulo_ja_existe = any(
            banca['titulo'] == titulo
            for banca in bancas
        )
        
        if not titulo_ja_existe and ano > ano_limite:
            bancas.append(banca_normalizada)
        
    return bancas
    
def normalizar_projetos(projetos_site):
    projetos = []
    for projeto in projetos_site:
        if int(projeto['ano']) > ano_limite:
            projetos.append(projeto)
    return projetos

def parece_nome(segmento):
    """Heurística: nome de pessoa = poucas palavras, maioria capitalizada,
    com conectores comuns em nomes (de, da, do, dos, das)."""
    segmento = segmento.strip()
    if not segmento:
        return False
    palavras = segmento.split()
    if len(palavras) > 6:
        return False
    conectores = {'de', 'da', 'do', 'dos', 'das', 'e'}
    for p in palavras:
        p_limpo = re.sub(r'[^\wÀ-ÿ]', '', p)
        if not p_limpo:
            continue
        if p_limpo.lower() in conectores:
            continue
        if not p_limpo[:1].isupper():
            return False
    return True

def extrair_evento_site(item_texto):
    # Categoria 'Publicação em evento': ano, autores, titulo, veiculo, tipo
    ano, resto = item_texto.split(',', 1)
    ano = ano.strip()

    resto, tipo = resto.rsplit(',', 1)
    tipo = tipo.strip()

    resto, veiculo = resto.rsplit(',', 1)
    veiculo = veiculo.strip()

    partes_meio = [p.strip() for p in resto.split(',')]

    if partes_meio[0] == '':
        autores = None
        titulo = ','.join(partes_meio[1:]).strip(', ').strip()
    else:
        autores_partes = []
        i = 0
        while i < len(partes_meio) and parece_nome(partes_meio[i]):
            autores_partes.append(partes_meio[i])
            i += 1
        # salvaguarda: se consumiu tudo (não sobrou nada pro titulo),
        # devolve o último pedaço como titulo
        if i >= len(partes_meio):
            i = len(partes_meio) - 1
            autores_partes = autores_partes[:-1]

        autores = ', '.join(autores_partes) if autores_partes else None
        titulo = ', '.join(partes_meio[i:]).strip()

    return {
        'ano': int(ano) if ano else None,
        'autores': autores if autores else None,
        'titulo': titulo if titulo else None,
        'veiculo': veiculo if veiculo else None,
        'tipo': tipo if tipo else None,
    }
    
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
    'Participações em Bancas de Cursos' : ['participacao_banca'],
    'Livros' : ['livro'],
    'Produções Tecnológicas' : ['']
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
                        extraido = extrair_evento_site(item_texto)
                        if extraido and normalizar_titulo(extraido['titulo']) == titulo_norm:
                            if extraido['autores']:
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
                if extraido and extraido['ano'] > ano_limite:
                    resultado_por_tipo.setdefault(tipo_padrao, []).append({
                        'titulo': extraido['titulo'],
                        'autores': extraido['autores'],
                        'ano' : extraido['ano'],
                        'issn': extraido['issn'],
                    })
            elif categoria_site == 'Capítulos de Livros':
                ano = int (re.sub(r'^(\d{4}).*$', r'\1', item_texto))
                if ano < ano_limite : break
                resultado_por_tipo.setdefault(tipo_padrao, []).append({
                    'titulo': re.sub(r'^\d{4},\s*', '', item_texto),
                    'ano': ano,
                })        
            
            elif categoria_site == 'Publicação em Eventos':
                extraido = extrair_evento_site(item_texto)
                if extraido and int(extraido['ano']) > ano_limite:
                    resultado_por_tipo.setdefault(tipo_padrao, []).append({
                        'titulo': extraido['titulo'],
                        'autores':extraido['autores'],
                        'fonte': 'siete',
                        'ano' : extraido['ano']
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
            'ano': ic.get('ano_inicio'),
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
def unir_projetos(projetos_lattes, projetos_sigaa):

    projetos_unificados = []
    titulos_encontrados = set()

    # Adiciona os projetos do Lattes
    for projeto_lattes in projetos_lattes:

        nome_lattes = projeto_lattes.get('nome', '')
        nome_normalizado = normalizar_titulo(nome_lattes)

        projeto_unificado = {
            'id': projeto_lattes.get('id'),
            'tipo': projeto_lattes.get('tipo'),
            'titulo': nome_lattes,
            'ano_inicio': projeto_lattes.get('ano_inicio'),
            'ano_conclusao': projeto_lattes.get('ano_conclusao'),
            'situacao': projeto_lattes.get('situacao'),
            'descricao': projeto_lattes.get('descricao'),
            'papel': projeto_lattes.get('papel'),
            'codigo': None,
            'areaConhecimento': None
        }

        # Procura o mesmo projeto no SIGAA
        for projeto_sigaa in projetos_sigaa:

            titulo_sigaa = projeto_sigaa.get('titulo', '')

            if normalizar_titulo(titulo_sigaa) == nome_normalizado:

                projeto_unificado['codigo'] = projeto_sigaa.get('codigo')
                projeto_unificado['areaConhecimento'] = (projeto_sigaa.get('areaConhecimento'))
                titulos_encontrados.add(normalizar_titulo(titulo_sigaa))
                break

        projetos_unificados.append(projeto_unificado)

    # Adiciona projetos que existem apenas no SIGAA
    for projeto_sigaa in projetos_sigaa:

        titulo_sigaa = projeto_sigaa.get('titulo', '')
        titulo_normalizado = normalizar_titulo(titulo_sigaa)

        if titulo_normalizado not in titulos_encontrados:

            projetos_unificados.append({
                'id': None,
                'tipo': 'pesquisa',
                'titulo': titulo_sigaa,
                'ano_inicio': int(projeto_sigaa.get('ano')),
                'ano_conclusao': None,
                'situacao': None,
                'descricao': None,
                'papel': None,
                'codigo': projeto_sigaa.get('codigo'),
                'areaConhecimento': projeto_sigaa.get(
                    'areaConhecimento'
                )
            })

    return projetos_unificados

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
        'projetos': unir_projetos(prof_lattes.get('projetos', []), normalizar_projetos(prof_site.get('sigaa', {}).get('projetosPesquisa', []))),
        'iniciacaoCientifica': iniciacao_cientifica,
        'participacao_bancas' : obter_categoria(prof_site, 'Participações em Bancas de Cursos'),
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
    
    