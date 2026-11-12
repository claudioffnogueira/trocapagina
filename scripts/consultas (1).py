"""
TrocaPágina - consultas implementadas como pipelines de agregação.

Cada função recebe o banco ("db") e devolve o resultado de um pipeline.
Os mesmos pipelines podem ser montados, stage por stage, na aba "Aggregations"
do MongoDB Atlas (veja o README e a pasta pipelines/).

Uso:
    python scripts/consultas.py
"""

import os
import sys

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError

NOME_BANCO = "trocapagina"

# ---------------------------------------------------------------------------
# Funcionalidade 1 - Livros parados
#   Livros disponíveis que nunca receberam interesse, com o nome do dono e há
#   quantos dias estão anunciados. Ajuda o dono a rever descrição ou preço.
#   Parte de "livros" e procura (sem achar) nos arrays de "usuarios".
# ---------------------------------------------------------------------------
PIPELINE_LIVROS_PARADOS = [
    # 1. só livros que ainda estão disponíveis
    {"$match": {"status": "disponivel"}},
    # 2. busca usuários com interesse no livro (array embutido)
    {"$lookup": {
        "from": "usuarios",
        "localField": "_id",
        "foreignField": "interesses.livroId",
        "as": "interessados",
    }},
    # 3. fica só com os livros que ninguém quis
    {"$match": {"interessados": {"$size": 0}}},
    # 4. traz o dono do livro
    {"$lookup": {
        "from": "usuarios",
        "localField": "proprietarioId",
        "foreignField": "_id",
        "as": "dono",
    }},
    {"$unwind": "$dono"},
    # 5. calcula há quantos dias o livro está anunciado
    {"$addFields": {"diasAnunciado": {"$floor": {"$divide": [
        {"$subtract": ["$$NOW", "$dataCadastro"]}, 86400000]}}}},
    # 6. formata a saída
    {"$project": {"_id": 0, "titulo": 1, "autor": 1, "genero": 1,
                  "dono": "$dono.nome", "cidade": "$dono.cidade",
                  "diasAnunciado": 1}},
    # 7. os mais antigos primeiro
    {"$sort": {"diasAnunciado": -1}},
]


# ---------------------------------------------------------------------------
# Funcionalidade 2 - Catálogo com filtros
#   Livros disponíveis filtrados por cidade do dono, gênero e modalidade
#   (troca, venda ou emprestimo). Todos os filtros são opcionais.
#   Parte de "livros" e traz o dono por $lookup.
# ---------------------------------------------------------------------------
def pipeline_catalogo(cidade=None, genero=None, modalidade=None):
    filtro_livro = {"status": "disponivel"}
    if genero:
        filtro_livro["genero"] = genero
    if modalidade:
        filtro_livro["modalidades.tipo"] = modalidade

    pipeline = [
        # 1. filtros do próprio livro (feitos antes do lookup, mais eficiente)
        {"$match": filtro_livro},
        # 2. traz o dono
        {"$lookup": {
            "from": "usuarios",
            "localField": "proprietarioId",
            "foreignField": "_id",
            "as": "dono",
        }},
        {"$unwind": "$dono"},
    ]
    # 3. filtro pela cidade do dono
    if cidade:
        pipeline.append({"$match": {"dono.cidade": cidade}})
    pipeline += [
        # 4. formata a saída
        {"$project": {"_id": 0, "titulo": 1, "autor": 1, "genero": 1,
                      "estadoConservacao": 1, "modalidades": 1,
                      "dono": "$dono.nome", "cidade": "$dono.cidade"}},
        # 5. ordem alfabética
        {"$sort": {"titulo": 1}},
    ]
    return pipeline


def livros_parados(db):
    return list(db.livros.aggregate(PIPELINE_LIVROS_PARADOS))


def catalogo(db, cidade=None, genero=None, modalidade=None):
    return list(db.livros.aggregate(pipeline_catalogo(cidade, genero, modalidade)))


def main():
    load_dotenv()
    uri = os.getenv("MONGODB_URI")
    if not uri:
        sys.exit("Erro: defina MONGODB_URI (veja o arquivo .env.example).")
    try:
        db = MongoClient(uri, serverSelectionTimeoutMS=10000)[NOME_BANCO]

        print("Funcionalidade 1 - Livros parados (sem nenhum interesse)")
        for linha in livros_parados(db):
            print(" ", linha)

        print("\nFuncionalidade 2 - Catálogo: Uberlândia, modalidade troca")
        for linha in catalogo(db, cidade="Uberlândia", modalidade="troca"):
            print(" ", linha)

        print("\nFuncionalidade 2 - Catálogo: gênero Romance (sem outros filtros)")
        for linha in catalogo(db, genero="Romance"):
            print(" ", linha)
    except PyMongoError as erro:
        sys.exit(f"Erro do MongoDB: {erro}")


if __name__ == "__main__":
    main()
