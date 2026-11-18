"""
TrocaPágina - execução dos pipelines de agregação no MongoDB Atlas.

Lê os arquivos JSON da pasta "pipelines/" e executa as consultas de agregação
na coleção "livros":
  1. pipelines/catalogo_filtros.json -> livros disponíveis para troca por cidade
  2. pipelines/livros_parados.json   -> livros disponíveis sem nenhum interesse

Uso:
    python scripts/executar_pipelines.py
    python scripts/executar_pipelines.py --cidade "Uberlândia" --modalidade troca
    python scripts/executar_pipelines.py --genero Romance
"""
from __future__ import annotations

import argparse
import copy
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


def carregar_pipeline(nome_arquivo: str) -> list[dict]:
    """Carrega um pipeline de agregação a partir da pasta pipelines/."""
    caminho = PASTA_PIPELINES / nome_arquivo
    if not caminho.exists():
        sys.exit(f"Erro: arquivo de pipeline não encontrado: {caminho}")
    with open(caminho, "r", encoding="utf-8") as arquivo:
        return json.load(arquivo)


def consultar_catalogo_filtros(
    db,
    cidade: str | None = None,
    modalidade: str | None = None,
    genero: str | None = None,
) -> list[dict]:
    """
    Executa pipelines/catalogo_filtros.json na coleção 'livros'.
    Se cidade, modalidade ou genero forem informados, ajusta os stages $match
    dinamicamente mantendo o restante do pipeline original.
    """
    pipeline = copy.deepcopy(carregar_pipeline("catalogo_filtros.json"))

    # Stage 0: $match inicial na coleção 'livros'
    match_livro = pipeline[0]["$match"]
    if modalidade:
        match_livro["modalidades.tipo"] = modalidade
    if genero:
        match_livro["genero"] = genero

    # Stage 3: $match após o $lookup/$unwind do proprietário ('dono')
    if cidade:
        pipeline[3]["$match"]["dono.cidade"] = cidade

    return list(db[COLECAO_ALVO].aggregate(pipeline))


def consultar_livros_parados(db) -> list[dict]:
    """Executa pipelines/livros_parados.json na coleção 'livros'."""
    pipeline = carregar_pipeline("livros_parados.json")
    return list(db[COLECAO_ALVO].aggregate(pipeline))


def exibir_catalogo(resultados: list[dict]) -> None:
    print("=== 1) Catálogo com Filtros ===")
    if not resultados:
        print("  Nenhum livro encontrado para os filtros informados.\n")
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
    parser = argparse.ArgumentParser(
        description="Executa os pipelines de agregação do TrocaPágina."
    )
    parser.add_argument(
        "--cidade",
        help="Sobrescreve a cidade do proprietário no filtro (padrão do JSON: Uberlândia)",
    )
    parser.add_argument(
        "--modalidade",
        choices=["troca", "venda", "emprestimo"],
        help="Sobrescreve a modalidade desejada (padrão do JSON: troca)",
    )
    parser.add_argument(
        "--genero",
        help="Adiciona filtro opcional por gênero literário (ex.: Romance, História)",
    )
    args = parser.parse_args()

    try:
        cliente = conectar()
        db = cliente[NOME_BANCO]

        catalogo = consultar_catalogo_filtros(
            db,
            cidade=args.cidade,
            modalidade=args.modalidade,
            genero=args.genero,
        )
        exibir_catalogo(catalogo)

        parados = consultar_livros_parados(db)
        exibir_livros_parados(parados)

        cliente.close()
    except PyMongoError as erro:
        sys.exit(f"Erro do MongoDB: {erro}")


if __name__ == "__main__":
    main()
