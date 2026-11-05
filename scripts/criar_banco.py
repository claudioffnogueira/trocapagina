"""
TrocaPágina - criação do banco de dados no MongoDB Atlas.

O script:
  1. conecta ao cluster usando a variável de ambiente MONGODB_URI;
  2. cria o banco "trocapagina" e as coleções "usuarios" e "livros", cada uma com
     validação de esquema ($jsonSchema). Os interesses dos usuários em livros
     ficam EMBUTIDOS no documento do usuário (array "interesses");
  3. cria os índices necessários;
  4. insere documentos de exemplo (somente se a coleção estiver vazia).

Uso:
    python scripts/criar_banco.py            # cria/atualiza e popula, sem apagar nada
    python scripts/criar_banco.py --reset    # apaga as coleções e recria tudo
"""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from pymongo import ASCENDING, TEXT, MongoClient
from pymongo.errors import PyMongoError

NOME_BANCO = "trocapagina"

ESTADOS_CONSERVACAO = ["novo", "ótimo", "bom", "regular", "desgastado"]
TIPOS_MODALIDADE = ["troca", "venda", "emprestimo"]
STATUS_LIVRO = ["disponivel", "reservado", "indisponivel"]
STATUS_INTERESSE = ["pendente", "aceito", "recusado"]


# --------------------------------------------------------------------------
# Esquemas de validação
# --------------------------------------------------------------------------
SCHEMA_USUARIOS = {
    "bsonType": "object",
    "required": ["nome", "email", "cidade", "estado", "dataCadastro", "ativo"],
    "properties": {
        "nome": {"bsonType": "string", "minLength": 2},
        "email": {"bsonType": "string", "pattern": "^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$"},
        "cidade": {"bsonType": "string"},
        "estado": {"bsonType": "string", "minLength": 2, "maxLength": 2},
        "dataCadastro": {"bsonType": "date"},
        "ativo": {"bsonType": "bool"},
        # Interesses do usuário em livros (embutidos no próprio usuário)
        "interesses": {
            "bsonType": "array",
            "items": {
                "bsonType": "object",
                "required": [
                    "livroId", "modalidadeDesejada", "status", "dataCriacao",
                ],
                "properties": {
                    "livroId": {"bsonType": "objectId"},
                    "modalidadeDesejada": {"enum": TIPOS_MODALIDADE},
                    "mensagem": {"bsonType": "string"},
                    "status": {"enum": STATUS_INTERESSE},
                    "dataCriacao": {"bsonType": "date"},
                },
            },
        },
    },
}

SCHEMA_LIVROS = {
    "bsonType": "object",
    "required": [
        "titulo", "autor", "genero", "estadoConservacao",
        "modalidades", "status", "proprietarioId", "dataCadastro",
    ],
    "properties": {
        "titulo": {"bsonType": "string", "minLength": 1},
        "autor": {"bsonType": "string", "minLength": 1},
        "genero": {"bsonType": "string"},
        "anoPublicacao": {"bsonType": "int", "minimum": 1000},
        "descricao": {"bsonType": "string"},
        "estadoConservacao": {"enum": ESTADOS_CONSERVACAO},
        "status": {"enum": STATUS_LIVRO},
        "proprietarioId": {"bsonType": "objectId"},
        "dataCadastro": {"bsonType": "date"},
        "modalidades": {
            "bsonType": "array",
            "minItems": 1,
            "items": {
                "bsonType": "object",
                "required": ["tipo"],
                "properties": {
                    "tipo": {"enum": TIPOS_MODALIDADE},
                    "preco": {"bsonType": ["double", "int", "decimal"], "minimum": 0},
                    "prazoDias": {"bsonType": "int", "minimum": 1},
                    "aceitaEmTroca": {"bsonType": "string"},
                },
            },
        },
    },
}

COLECOES = {
    "usuarios": SCHEMA_USUARIOS,
    "livros": SCHEMA_LIVROS,
}

# Coleção da primeira versão do projeto, que não existe mais (os interesses
# agora ficam dentro de "usuarios"). É removida no --reset.
COLECAO_ANTIGA = "interesses"


# --------------------------------------------------------------------------
# Funções auxiliares
# --------------------------------------------------------------------------
def conectar():
    """Lê MONGODB_URI (do ambiente ou do arquivo .env) e conecta ao cluster."""
    load_dotenv()
    uri = os.getenv("MONGODB_URI")
    if not uri:
        sys.exit("Erro: defina MONGODB_URI (veja o arquivo .env.example).")
    cliente = MongoClient(uri, serverSelectionTimeoutMS=10000)
    cliente.admin.command("ping")  # falha cedo se a conexão não funcionar
    return cliente


def garantir_colecao(db, nome, schema):
    """Cria a coleção com validação; se já existir, apenas atualiza a validação."""
    validador = {"$jsonSchema": schema}
    if nome not in db.list_collection_names():
        db.create_collection(nome, validator=validador, validationAction="error")
        print(f"  coleção '{nome}' criada")
    else:
        db.command("collMod", nome, validator=validador, validationLevel="strict")
        print(f"  coleção '{nome}' já existia (validação atualizada)")


def criar_indices(db):
    """Índices para os acessos mais comuns do sistema."""
    # Não pode haver dois usuários com o mesmo e-mail
    db.usuarios.create_index([("email", ASCENDING)], unique=True, name="uniq_email")

    # Busca textual por título/autor e filtros por status/gênero
    db.livros.create_index(
        [("titulo", TEXT), ("autor", TEXT)],
        default_language="portuguese", name="texto_titulo_autor",
    )
    db.livros.create_index(
        [("status", ASCENDING), ("genero", ASCENDING)], name="status_genero"
    )
    db.livros.create_index([("proprietarioId", ASCENDING)], name="proprietario")

    # Descobrir quem se interessou por um livro (busca dentro do array
    # embutido "interesses" dos usuários)
    db.usuarios.create_index(
        [("interesses.livroId", ASCENDING)], name="interesses_livro"
    )
    print("  índices criados")


# --------------------------------------------------------------------------
# Documentos de exemplo (todos os dados são fictícios)
# --------------------------------------------------------------------------
def popular_usuarios(db, agora):
    if db.usuarios.count_documents({}) > 0:
        print("  'usuarios' já possui documentos; exemplos não inseridos")
        return None
    docs = [
        {"nome": "Ana Beatriz Lima", "email": "ana.lima@example.com",
         "cidade": "Uberlândia", "estado": "MG",
         "dataCadastro": agora - timedelta(days=90), "ativo": True},
        {"nome": "Carlos Eduardo Souza", "email": "carlos.souza@example.com",
         "cidade": "Uberlândia", "estado": "MG",
         "dataCadastro": agora - timedelta(days=60), "ativo": True},
        {"nome": "Marina Tavares", "email": "marina.tavares@example.com",
         "cidade": "Araguari", "estado": "MG",
         "dataCadastro": agora - timedelta(days=30), "ativo": True},
        {"nome": "João Pedro Alves", "email": "joao.alves@example.com",
         "cidade": "Uberaba", "estado": "MG",
         "dataCadastro": agora - timedelta(days=10), "ativo": True},
    ]
    ids = db.usuarios.insert_many(docs).inserted_ids
    print(f"  {len(ids)} usuários inseridos")
    return ids


def popular_livros(db, agora, u):
    if u is None or db.livros.count_documents({}) > 0:
        print("  'livros' não populada (já possui documentos ou sem usuários novos)")
        return None
    ana, carlos, marina, joao = u
    docs = [
        {"titulo": "Dom Casmurro", "autor": "Machado de Assis",
         "genero": "Romance", "anoPublicacao": 1899,
         "descricao": "Edição de bolso, sem anotações.",
         "estadoConservacao": "bom", "status": "disponivel",
         "modalidades": [
             {"tipo": "troca", "aceitaEmTroca": "Romances brasileiros"},
             {"tipo": "venda", "preco": 18.5},
         ],
         "proprietarioId": ana, "dataCadastro": agora - timedelta(days=80)},
        {"titulo": "O Hobbit", "autor": "J. R. R. Tolkien",
         "genero": "Fantasia", "anoPublicacao": 1937,
         "descricao": "Capa dura, pequenas marcas de uso nas bordas.",
         "estadoConservacao": "ótimo", "status": "reservado",
         "modalidades": [{"tipo": "emprestimo", "prazoDias": 30}],
         "proprietarioId": ana, "dataCadastro": agora - timedelta(days=70)},
        {"titulo": "Capitães da Areia", "autor": "Jorge Amado",
         "genero": "Romance", "anoPublicacao": 1937,
         "estadoConservacao": "regular", "status": "disponivel",
         "modalidades": [{"tipo": "venda", "preco": 12.0}],
         "proprietarioId": carlos, "dataCadastro": agora - timedelta(days=50)},
        {"titulo": "Sapiens: Uma Breve História da Humanidade",
         "autor": "Yuval Noah Harari", "genero": "História",
         "anoPublicacao": 2011,
         "estadoConservacao": "novo", "status": "disponivel",
         "modalidades": [
             {"tipo": "troca", "aceitaEmTroca": "Livros de ciência ou história"},
             {"tipo": "emprestimo", "prazoDias": 21},
         ],
         "proprietarioId": carlos, "dataCadastro": agora - timedelta(days=40)},
        {"titulo": "Código Limpo", "autor": "Robert C. Martin",
         "genero": "Tecnologia", "anoPublicacao": 2008,
         "descricao": "Algumas páginas grifadas a lápis.",
         "estadoConservacao": "bom", "status": "disponivel",
         "modalidades": [{"tipo": "venda", "preco": 45.0}],
         "proprietarioId": marina, "dataCadastro": agora - timedelta(days=20)},
        {"titulo": "A Hora da Estrela", "autor": "Clarice Lispector",
         "genero": "Romance", "anoPublicacao": 1977,
         "estadoConservacao": "desgastado", "status": "disponivel",
         "modalidades": [
             {"tipo": "troca", "aceitaEmTroca": "Qualquer livro de contos"},
             {"tipo": "emprestimo", "prazoDias": 15},
         ],
         "proprietarioId": joao, "dataCadastro": agora - timedelta(days=5)},
    ]
    ids = db.livros.insert_many(docs).inserted_ids
    print(f"  {len(ids)} livros inseridos")
    return ids


def popular_interesses(db, agora, u, l):
    """Embute os interesses dentro dos documentos dos usuários."""
    if u is None or l is None:
        print("  interesses não inseridos (usuários/livros já existiam)")
        return
    ana, carlos, marina, joao = u
    dom_casmurro, hobbit, capitaes, sapiens, codigo, hora_estrela = l
    interesses_por_usuario = {
        carlos: [
            {"livroId": hobbit, "modalidadeDesejada": "emprestimo",
             "mensagem": "Gostaria de ler durante as férias!",
             "status": "aceito", "dataCriacao": agora - timedelta(days=6)},
            {"livroId": hora_estrela, "modalidadeDesejada": "emprestimo",
             "status": "pendente", "dataCriacao": agora - timedelta(days=1)},
        ],
        marina: [
            {"livroId": dom_casmurro, "modalidadeDesejada": "venda",
             "mensagem": "Ainda está disponível?",
             "status": "pendente", "dataCriacao": agora - timedelta(days=3)},
        ],
        joao: [
            {"livroId": sapiens, "modalidadeDesejada": "troca",
             "mensagem": "Posso oferecer A Hora da Estrela em troca.",
             "status": "pendente", "dataCriacao": agora - timedelta(days=2)},
        ],
        ana: [
            {"livroId": codigo, "modalidadeDesejada": "venda",
             "status": "recusado", "dataCriacao": agora - timedelta(days=1)},
        ],
    }
    total = 0
    for usuario_id, interesses in interesses_por_usuario.items():
        db.usuarios.update_one(
            {"_id": usuario_id}, {"$set": {"interesses": interesses}}
        )
        total += len(interesses)
    print(f"  {total} interesses embutidos nos usuários")


# --------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Cria o banco do TrocaPágina.")
    parser.add_argument("--reset", action="store_true",
                        help="apaga as coleções existentes antes de recriar")
    args = parser.parse_args()

    try:
        cliente = conectar()
        db = cliente[NOME_BANCO]

        if args.reset:
            print("Removendo coleções existentes...")
            for nome in list(COLECOES) + [COLECAO_ANTIGA]:
                db.drop_collection(nome)

        if COLECAO_ANTIGA in db.list_collection_names():
            print(f"Aviso: existe a coleção antiga '{COLECAO_ANTIGA}'. "
                  "Rode com --reset para removê-la e recriar tudo.")

        print(f"Criando banco '{NOME_BANCO}' e coleções...")
        for nome, schema in COLECOES.items():
            garantir_colecao(db, nome, schema)
        criar_indices(db)

        print("Inserindo documentos de exemplo...")
        agora = datetime.now(timezone.utc)
        usuarios = popular_usuarios(db, agora)
        livros = popular_livros(db, agora, usuarios)
        popular_interesses(db, agora, usuarios, livros)

        print("\nResumo:")
        for nome in COLECOES:
            print(f"  {nome}: {db[nome].count_documents({})} documento(s)")
        com_interesse = db.usuarios.count_documents({"interesses.0": {"$exists": True}})
        print(f"  (usuários com interesses embutidos: {com_interesse})")
    except PyMongoError as erro:
        sys.exit(f"Erro do MongoDB: {erro}")


if __name__ == "__main__":
    main()
