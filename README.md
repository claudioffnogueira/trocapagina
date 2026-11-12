# 📚 TrocaPágina

> *Um espaço para fazer livros circularem.*

## 1. Descrição do sistema

**TrocaPágina** é uma plataforma para que pessoas disponibilizem livros usados
para **troca, venda ou empréstimo**.

**Funcionalidade principal:** permitir que usuários disponibilizem livros para
troca, venda ou empréstimo.

**Como funciona:** o usuário cadastra um livro, informa seu estado de
conservação e escolhe como deseja disponibilizá-lo (uma ou mais modalidades).
Outros usuários podem encontrar o livro e demonstrar interesse.

**Objetivo:** facilitar o acesso a livros usados, incentivar a leitura e dar
novas oportunidades aos livros que estão parados.

### Principais entidades

| Entidade | Papel no sistema |
|---|---|
| **Usuário** | Pessoa cadastrada, que pode anunciar livros e demonstrar interesse em livros de outros. |
| **Livro** | Exemplar anunciado por um usuário, com estado de conservação, modalidades (troca/venda/empréstimo) e status. |
| **Interesse** | Manifestação de interesse de um usuário em um livro, para uma modalidade específica. Fica embutido no documento do usuário. |

### Tecnologias

| Tecnologia | Uso |
|---|---|
| **MongoDB Atlas** | Banco principal: usuários, livros e interesses. |
| **Redis Cloud** | Cache de sessão, limite de tentativas de login e estruturas probabilísticas (Bloom Filter, HyperLogLog, Count-Min Sketch, Top-K). |
| **Python 3.9+** | Scripts de criação do banco e demonstração do Redis (`pymongo`, `redis`, `python-dotenv`). |

## 2. Banco de dados (MongoDB Atlas)

- **Banco:** `trocapagina`
- **Coleções:** `usuarios`, `livros`

### Decisões de modelagem

- **Modalidades embutidas no livro.** Um livro pode ser ofertado de mais de um
  jeito (ex.: troca *e* venda). Como as modalidades só fazem sentido dentro do
  livro e são sempre lidas junto com ele, ficam embutidas (array `modalidades`).
- **Interesses embutidos no usuário.** Cada usuário guarda no array `interesses`
  os livros em que demonstrou interesse (`livroId`, modalidade desejada,
  mensagem, status e data). Isso permite listar "meus interesses" com uma única
  leitura. Para descobrir quem se interessou por um livro, usa-se o índice
  multikey `interesses.livroId`.
- **Referências entre coleções.** `livros.proprietarioId` referencia
  `usuarios._id`, e `usuarios.interesses[].livroId` referencia `livros._id`.
  Usuários e livros mudam de forma independente, então não são duplicados um
  dentro do outro.
- **Validação de esquema** (`$jsonSchema`) nas duas coleções: o próprio banco
  rejeita documentos fora do formato (ex.: estado de conservação inválido).
- **Índices:**
  - `usuarios`: e-mail único (`uniq_email`) e `interesses.livroId`
    (`interesses_livro`);
  - `livros`: busca textual por título/autor em português
    (`texto_titulo_autor`), filtro por status/gênero (`status_genero`) e
    `proprietarioId` (`proprietario`).

> **Limitação conhecida:** com interesses embutidos, o banco não impede que o
> mesmo usuário registre o mesmo interesse (mesmo livro e modalidade) mais de
> uma vez. Essa regra deve ser garantida pela aplicação (por exemplo, atualizar
> só se ainda não existir um interesse com aquele `livroId`).

### Valores aceitos

| Campo | Valores |
|---|---|
| `livros.estadoConservacao` | `novo`, `ótimo`, `bom`, `regular`, `desgastado` |
| `livros.status` | `disponivel`, `reservado`, `indisponivel` |
| `livros.modalidades[].tipo` | `troca`, `venda`, `emprestimo` |
| `usuarios.interesses[].modalidadeDesejada` | `troca`, `venda`, `emprestimo` |
| `usuarios.interesses[].status` | `pendente`, `aceito`, `recusado` |

### Exemplos de documentos

**`usuarios`** (com interesses embutidos)
```json
{
  "_id": { "$oid": "..." },
  "nome": "Carlos Eduardo Souza",
  "email": "carlos.souza@example.com",
  "cidade": "Uberlândia",
  "estado": "MG",
  "dataCadastro": { "$date": "2026-09-13T12:00:00Z" },
  "ativo": true,
  "interesses": [
    {
      "livroId": { "$oid": "<_id de livros>" },
      "modalidadeDesejada": "emprestimo",
      "mensagem": "Gostaria de ler durante as férias!",
      "status": "aceito",
      "dataCriacao": { "$date": "2026-11-06T12:00:00Z" }
    }
  ]
}
```

**`livros`**
```json
{
  "_id": { "$oid": "..." },
  "titulo": "Dom Casmurro",
  "autor": "Machado de Assis",
  "genero": "Romance",
  "anoPublicacao": 1899,
  "descricao": "Edição de bolso, sem anotações.",
  "estadoConservacao": "bom",
  "status": "disponivel",
  "modalidades": [
    { "tipo": "troca", "aceitaEmTroca": "Romances brasileiros" },
    { "tipo": "venda", "preco": 18.5 }
  ],
  "proprietarioId": { "$oid": "<_id de usuarios>" },
  "dataCadastro": { "$date": "2026-08-24T12:00:00Z" }
}
```

O script `scripts/criar_banco.py` insere **4 usuários, 6 livros e 5 interesses**
fictícios (veja o código para todos os exemplos).

### Consultas de agregação (`pipelines/`)

Os pipelines estão em JSON e podem ser colados na aba **Aggregations** do
MongoDB Compass / Atlas (ou executados com `db.<coleção>.aggregate([...])`).
Ambos devem ser executados na coleção **`livros`**.

| Arquivo | O que faz |
|---|---|
| `pipelines/catalogo_filtros.json` | Lista livros **disponíveis para troca** cujo dono mora em Uberlândia, com nome e cidade do dono, ordenados por título. |
| `pipelines/livros_parados.json` | Lista livros **disponíveis que ainda não receberam nenhum interesse**, com há quantos dias estão anunciados (do mais antigo ao mais recente). |

## 3. Redis (cache e estatísticas)

O script `scripts/redis_cache.py` demonstra o uso do Redis Cloud como camada
de apoio ao MongoDB. Cada estrutura resolve um problema diferente:

| Estrutura | Chave | Para que serve |
|---|---|---|
| **String com TTL** | `sessao:<token>` | Cache da sessão de login. A autenticação de verdade continua no MongoDB; o Redis guarda a sessão já validada e ela expira sozinha em 1 hora. |
| **Contador com TTL** | `tentativas:<email>` | Limite de tentativas de login erradas: 5 falhas dentro de 15 minutos bloqueiam o login. |
| **Bloom Filter** | `emails_cadastrados` | "Este e-mail já está cadastrado?" sem consultar o MongoDB. Resposta `0` = com certeza não existe; `1` = provavelmente existe (confirmar no MongoDB). |
| **HyperLogLog** | `usuarios_unicos:<AAAA-MM-DD>` | Quantos usuários **únicos** acessaram o sistema por dia (e em vários dias juntos). Repetir o mesmo usuário não aumenta a contagem. |
| **Count-Min Sketch** | `visualizacoes_livros` | Estimativa de quantas vezes cada livro foi visualizado (nunca subestima, pode superestimar um pouco). |
| **Top-K** | `top_livros` | Os 3 livros mais visualizados (complementa o CMS, que não lista itens). |

> ⚠️ A função `demo()` **apaga as chaves acima** antes de rodar, para que o
> script possa ser executado várias vezes. Não a execute em um banco Redis que
> contenha dados reais.

### Evidências (`prints/redis/`)

| Arquivo | Conteúdo |
|---|---|
| `saida_script.png` | Saída da execução de `redis_cache.py`. |
| `chaves_redis.png` | Chaves criadas, vistas no Redis Insight. |
| `comandos_cli.png` | Comandos `BF.INFO`, `CMS.INFO`, `CMS.QUERY`, `TOPK.LIST` e `TTL` no CLI. |

## 4. Como executar

Pré-requisitos:

- Python 3.9+;
- um cluster no [MongoDB Atlas](https://www.mongodb.com/atlas) (o IP da sua
  máquina precisa estar liberado em *Network Access*);
- um banco no [Redis Cloud](https://redis.io/cloud/) com os módulos de
  probabilísticas (Bloom, Count-Min Sketch, Top-K) habilitados.

```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Configurar as conexões (NÃO versione o arquivo .env)
cp .env.example .env
#    edite o .env com a URI do MongoDB e os dados do Redis

# 3. Criar o banco, as coleções, os índices e os documentos de exemplo
python scripts/criar_banco.py

# (opcional) apagar as coleções e recriar tudo do zero
python scripts/criar_banco.py --reset

# 4. Demonstração do Redis
python scripts/redis_cache.py
```

No Windows, use `py` no lugar de `python` se necessário.

**Variáveis do `.env`:**

| Variável | Descrição |
|---|---|
| `MONGODB_URI` | URI de conexão do cluster Atlas. Se a senha tiver caracteres especiais (`@`, `:`, `/`, `#`...), codifique-os (URL encode). |
| `REDIS_HOST` | Endpoint do banco no Redis Cloud. |
| `REDIS_PORT` | Porta do banco. |
| `REDIS_USERNAME` | Usuário (normalmente `default`). |
| `REDIS_PASSWORD` | Senha do banco. |

**Sobre o `criar_banco.py`:**

- Pode ser executado mais de uma vez: coleções existentes têm só a validação
  atualizada, e os exemplos só são inseridos quando as coleções estão vazias.
- Os livros e interesses de exemplo dependem dos usuários recém-inseridos. Se
  uma execução falhar no meio do processo, use `--reset` para recomeçar.
- `--reset` **apaga** as coleções `usuarios` e `livros` (e a coleção antiga
  `interesses`, de uma versão anterior do projeto, se existir).

## 5. Estrutura do repositório

```
trocapagina/
├── README.md                      # descrição do sistema, banco e Redis
├── requirements.txt               # dependências Python
├── .env.example                   # modelo do arquivo de configuração
├── .gitignore                     # ignora o .env (credenciais)
├── scripts/
│   ├── criar_banco.py             # cria banco, coleções, índices e exemplos (MongoDB)
│   └── redis_cache.py             # demonstração de cache e estruturas do Redis
├── pipelines/
│   ├── catalogo_filtros.json      # livros para troca na cidade do dono
│   └── livros_parados.json        # livros disponíveis sem nenhum interesse
└── prints/
    └── redis/                     # evidências da execução no Redis Cloud
```

## 6. Segurança

As credenciais (URI do MongoDB e senha do Redis) ficam **apenas** no arquivo
`.env`, que está no `.gitignore`. Nunca coloque senhas diretamente no código,
em commits ou em arquivos compactados que serão compartilhados. Se uma
credencial for exposta, troque-a imediatamente no painel do Atlas ou do Redis
Cloud.

Todos os dados de exemplo são fictícios.
