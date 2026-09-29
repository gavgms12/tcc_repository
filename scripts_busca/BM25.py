from rank_bm25 import BM25Okapi
import argparse

def tokenizer_professores_bm25(perfis):
    corpus = [perfil.get("texto_embedding") for perfil in perfis]
    tokenized_corpus = [corpu.split(" ") for corpu in corpus]

    return BM25Okapi(tokenized_corpus)

def busca_bm25(perfis,bm25,aluno):
    tokenized_query = aluno.split(" ")
    return bm25.get_top_n(tokenized_query, perfis, n=2)

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Comparação perfis aluno com a base de professores usando BM25(lexical)"
    )
    # botar as infos aqui ou no processo total?
if __name__ == "__main__":
    main()