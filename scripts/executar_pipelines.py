"""
TrocaPágina - execução dos pipelines de agregação no MongoDB Atlas.

Lê os arquivos JSON da pasta "pipelines/" e executa as consultas de agregação
na coleção "livros":
  1. pipelines/catalogo_filtros.json -> livros disponíveis para troca em Uberlândia
  2. pipelines/livros_parados.json   -> livros disponíveis sem nenhum interesse

Uso:
    python scripts/executar_pipelines.py
"""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError

NOME_BANCO = "trocapagina"
COLECAO_ALVO = "livros"

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
PASTA_PIPELINES = RAIZ_PROJETO / "pipelines"


def conectar():
    """Lê MONGODB_URI (do ambiente ou do arquivo .env) e conecta ao cluster."""
    load_dotenv(RAIZ_PROJETO / ".env")
    uri = os.getenv("MONGODB_URI")
    if not uri:
        sys.exit("Erro: defina MONGODB_URI (veja o arquivo .env.example).")
    cliente = MongoClient(uri, serverSelectionTimeoutMS=10000)
    cliente.admin.command("ping")
    return cliente


def executar_pipeline(db, nome_arquivo: str) -> list[dict]:
    """Lê um arquivo JSON de pipeline e executa a agregação na coleção 'livros'."""
    caminho = PASTA_PIPELINES / nome_arquivo
    if not caminho.exists():
        sys.exit(f"Erro: arquivo de pipeline não encontrado: {caminho}")
    with open(caminho, "r", encoding="utf-8") as arquivo:
        pipeline = json.load(arquivo)
    return list(db[COLECAO_ALVO].aggregate(pipeline))


def exibir_catalogo(resultados: list[dict]) -> None:
    print("=== 1) Catálogo com Filtros ===")
    if not resultados:
        print("  Nenhum livro encontrado.\n")
        return

    for livro in resultados:
        modalidades = ", ".join(m["tipo"] for m in livro.get("modalidades", []))
        print(
            f"  - {livro['titulo']} ({livro['autor']}) | "
            f"Gênero: {livro['genero']} | Estado: {livro['estadoConservacao']} | "
            f"Modalidades: {modalidades} | "
            f"Dono: {livro['dono']} ({livro['cidade']})"
        )
    print(f"Total: {len(resultados)} livro(s)\n")


def exibir_livros_parados(resultados: list[dict]) -> None:
    print("=== 2) Livros Parados (sem nenhum interesse) ===")
    if not resultados:
        print("  Nenhum livro parado encontrado.\n")
        return

    for livro in resultados:
        print(
            f"  - {livro['titulo']} ({livro['autor']}) | "
            f"Gênero: {livro['genero']} | "
            f"Dono: {livro['dono']} ({livro['cidade']}) | "
            f"Anunciado há {livro['diasAnunciado']} dia(s)"
        )
    print(f"Total: {len(resultados)} livro(s)\n")


def main():
    try:
        cliente = conectar()
        db = cliente[NOME_BANCO]

        catalogo = executar_pipeline(db, "catalogo_filtros.json")
        exibir_catalogo(catalogo)

        parados = executar_pipeline(db, "livros_parados.json")
        exibir_livros_parados(parados)

        cliente.close()
    except PyMongoError as erro:
        sys.exit(f"Erro do MongoDB: {erro}")


if __name__ == "__main__":
    main()
