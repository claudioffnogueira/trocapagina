"""
TrocaPágina - cache de login e estatísticas de uso com Redis.

Estruturas usadas:
  - String com TTL ........ cache da sessão de login (expira sozinha)
  - Contador com TTL ...... limite de tentativas de login erradas
  - Bloom Filter (BF) ..... "este e-mail já está cadastrado?" sem ir ao MongoDB
  - HyperLogLog (HLL) ..... quantos usuários ÚNICOS acessaram o sistema por dia
  - Count-Min Sketch (CMS)  quantas vezes cada livro foi visualizado
  - Top-K ................. os livros mais visualizados (complemento do CMS)

Uso:
    python scripts/redis_cache.py
"""

import os
import secrets
import sys
from datetime import date, timedelta

import redis
from dotenv import load_dotenv
from redis.exceptions import RedisError, ResponseError

TTL_SESSAO = 3600            # sessão vale 1 hora
MAX_TENTATIVAS = 5           # falhas de login permitidas...
JANELA_BLOQUEIO = 900        # ...dentro de 15 minutos

CHAVE_BLOOM_EMAILS = "emails_cadastrados"
CHAVE_CMS_LIVROS = "visualizacoes_livros"
CHAVE_TOPK_LIVROS = "top_livros"


def conectar():
    """Lê as variáveis do .env e conecta ao Redis Cloud."""
    load_dotenv()
    host = os.getenv("REDIS_HOST")
    senha = os.getenv("REDIS_PASSWORD")
    if not host or not senha:
        sys.exit("Erro: defina REDIS_HOST e REDIS_PASSWORD (veja o .env.example).")
    r = redis.Redis(
        host=host,
        port=int(os.getenv("REDIS_PORT", 6379)),
        username=os.getenv("REDIS_USERNAME", "default"),
        password=senha,
        decode_responses=True,
        socket_connect_timeout=10,
    )
    r.ping()  # falha cedo se a conexão não funcionar
    return r


# ---------------------------------------------------------------------------
# 1. Cache de login (String com TTL)
#    A autenticação de verdade continua no MongoDB; o Redis só guarda a sessão
#    já validada, para as próximas requisições não consultarem o banco.
# ---------------------------------------------------------------------------
def criar_sessao(r, email):
    token = secrets.token_hex(16)
    r.set(f"sessao:{token}", email, ex=TTL_SESSAO)
    return token


def validar_sessao(r, token):
    """Devolve o e-mail dono da sessão, ou None se expirou/não existe."""
    return r.get(f"sessao:{token}")


def encerrar_sessao(r, token):
    """Logout: apaga a sessão antes de expirar."""
    r.delete(f"sessao:{token}")


def registrar_falha_login(r, email):
    """Conta uma tentativa errada; a contagem expira após a janela de bloqueio."""
    chave = f"tentativas:{email}"
    total = r.incr(chave)
    if total == 1:
        r.expire(chave, JANELA_BLOQUEIO)
    return total


def login_bloqueado(r, email):
    total = r.get(f"tentativas:{email}")
    return total is not None and int(total) >= MAX_TENTATIVAS


# ---------------------------------------------------------------------------
# 2. Bloom Filter - e-mails cadastrados
#    0 = com certeza NÃO existe. 1 = provavelmente existe (confirmar no Mongo).
# ---------------------------------------------------------------------------
def preparar_bloom(r, taxa_erro=0.01, capacidade=10000):
    try:
        r.bf().reserve(CHAVE_BLOOM_EMAILS, taxa_erro, capacidade)
    except ResponseError as erro:
        if "exists" not in str(erro).lower():
            raise


def registrar_email(r, email):
    r.bf().add(CHAVE_BLOOM_EMAILS, email)


def email_pode_existir(r, email):
    return bool(r.bf().exists(CHAVE_BLOOM_EMAILS, email))


# ---------------------------------------------------------------------------
# 3. HyperLogLog - usuários únicos por dia
#    Repetir o mesmo usuário não aumenta a contagem. ~12 KB por chave, com
#    erro de cerca de 0,8%.
# ---------------------------------------------------------------------------
def registrar_acesso(r, email, dia=None):
    dia = dia or date.today()
    r.pfadd(f"usuarios_unicos:{dia.isoformat()}", email)


def unicos_no_dia(r, dia=None):
    dia = dia or date.today()
    return r.pfcount(f"usuarios_unicos:{dia.isoformat()}")


def unicos_no_periodo(r, dias):
    """Únicos em vários dias juntos (um usuário que voltou conta uma vez só)."""
    return r.pfcount(*[f"usuarios_unicos:{d.isoformat()}" for d in dias])


# ---------------------------------------------------------------------------
# 4. Count-Min Sketch + Top-K - visualizações de livros
#    O CMS estima quantas vezes cada livro foi visto (nunca subestima, pode
#    superestimar um pouco). Ele não lista os itens, então o Top-K guarda os
#    mais vistos.
# ---------------------------------------------------------------------------
def preparar_contadores(r):
    try:
        r.cms().initbyprob(CHAVE_CMS_LIVROS, 0.001, 0.01)
    except ResponseError as erro:
        if "exists" not in str(erro).lower():
            raise
    try:
        r.topk().reserve(CHAVE_TOPK_LIVROS, 3, 50, 4, 0.9)
    except ResponseError as erro:
        if "exists" not in str(erro).lower():
            raise


def registrar_visualizacao(r, titulo, vezes=1):
    r.cms().incrby(CHAVE_CMS_LIVROS, [titulo], [vezes])
    r.topk().add(CHAVE_TOPK_LIVROS, *([titulo] * vezes))


def visualizacoes(r, *titulos):
    return dict(zip(titulos, r.cms().query(CHAVE_CMS_LIVROS, *titulos)))


def livros_mais_vistos(r):
    return r.topk().list(CHAVE_TOPK_LIVROS)


# ---------------------------------------------------------------------------
# Demonstração (usa os mesmos dados fictícios do criar_banco.py)
# ---------------------------------------------------------------------------
def demo(r):
    # começa do zero para o script poder rodar várias vezes
    hoje = date.today()
    ontem = hoje - timedelta(days=1)
    r.delete(CHAVE_BLOOM_EMAILS, CHAVE_CMS_LIVROS, CHAVE_TOPK_LIVROS,
             f"usuarios_unicos:{hoje.isoformat()}",
             f"usuarios_unicos:{ontem.isoformat()}",
             "tentativas:ana.lima@example.com")

    print("1) Cache de login")
    token = criar_sessao(r, "ana.lima@example.com")
    print("  sessão criada; dono:", validar_sessao(r, token),
          "| expira em", r.ttl(f"sessao:{token}"), "s")
    encerrar_sessao(r, token)
    print("  após logout:", validar_sessao(r, token))
    for _ in range(MAX_TENTATIVAS):
        registrar_falha_login(r, "ana.lima@example.com")
    print("  após", MAX_TENTATIVAS, "falhas, bloqueado?",
          login_bloqueado(r, "ana.lima@example.com"))

    print("\n2) Bloom Filter - e-mails cadastrados")
    preparar_bloom(r)
    for email in ["ana.lima@example.com", "carlos.souza@example.com",
                  "marina.tavares@example.com", "joao.alves@example.com"]:
        registrar_email(r, email)
    for email in ["ana.lima@example.com", "fulano@example.com"]:
        print(f"  {email}: pode existir? {email_pode_existir(r, email)}")

    print("\n3) HyperLogLog - usuários únicos")
    for email in ["ana.lima@example.com", "carlos.souza@example.com",
                  "ana.lima@example.com"]:          # Ana repete de propósito
        registrar_acesso(r, email, hoje)
    for email in ["marina.tavares@example.com", "ana.lima@example.com"]:
        registrar_acesso(r, email, ontem)
    print("  únicos hoje:", unicos_no_dia(r, hoje), "(Ana repetida conta uma vez)")
    print("  únicos ontem:", unicos_no_dia(r, ontem))
    print("  únicos nos 2 dias:", unicos_no_periodo(r, [ontem, hoje]))

    print("\n4) Count-Min Sketch + Top-K - visualizações de livros")
    preparar_contadores(r)
    for titulo, vezes in [("Dom Casmurro", 5), ("O Hobbit", 3),
                          ("Sapiens: Uma Breve História da Humanidade", 2),
                          ("Código Limpo", 1)]:
        registrar_visualizacao(r, titulo, vezes)
    print(" ", visualizacoes(r, "Dom Casmurro", "O Hobbit", "A Hora da Estrela"))
    print("  mais vistos:", livros_mais_vistos(r))


def main():
    try:
        r = conectar()
        demo(r)
    except RedisError as erro:
        sys.exit(f"Erro do Redis: {erro}")


if __name__ == "__main__":
    main()
