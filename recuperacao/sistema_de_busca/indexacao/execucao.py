from storage.minio_storage import ler_parquet_silver,ler_parquet_gold
from recuperacao.sistema_de_busca.indexacao.perfis import criar_perfis
from recuperacao.sistema_de_busca.textos import producao_montar_texto_para_modelo
from recuperacao.sistema_de_busca.database_vetores import conectar_Qdrant, criar_collection_qdrant,adicionar_trabalhos_qdrant
from recuperacao.sistema_de_busca.modelo import carregar_modelo,criar_representacao_densa_esparso
from dotenv import load_dotenv

load_dotenv()

ic_dados = ler_parquet_silver("trabalhos_ic_periodicos.parquet")

modelo = carregar_modelo()

ics_perfil = criar_perfis(ic_dados, producao_montar_texto_para_modelo, "id", ["titulo", "ano"])

ics_valores_denso_esparso = criar_representacao_densa_esparso(ics_perfil)

client = conectar_Qdrant

criar_collection_qdrant(client, "iniciacao_cientifica")

adicionar_trabalhos_qdrant(client,ics_perfil,ics_valores_denso_esparso,collection="iniciacao_cientifica")
