# 📚 TrocaPágina

> *Um espaço para fazer livros circularem.*

## 1. Descrição do sistema

**TrocaPágina** é uma plataforma para que pessoas disponibilizem livros usados
para **troca, venda ou empréstimo**.

**Funcionalidade principal:** permitir que usuários disponibilizem livros para
troca, venda ou empréstimo.

**Como funciona:** o usuário cadastra um livro, informa seu estado de
conservação e escolhe como deseja disponibilizá-lo (uma ou mais modalidades).
Outros usuários podem encontrar o livro e demonstrar interesse; cada interesse
fica registrado dentro do próprio usuário interessado.

**Objetivo:** facilitar o acesso a livros usados, incentivar a leitura e dar
novas oportunidades aos livros que estão parados.


## 2. Banco de dados (MongoDB Atlas)

- **Banco:** `trocapagina`
- **Coleções:** `usuarios` (com os interesses embutidos) e `livros`

### Decisões de modelagem

- **Modalidades embutidas no livro.** Um livro pode ser ofertado de mais de um
  jeito (ex.: troca *e* venda). Como as modalidades só fazem sentido dentro do
  livro e são sempre lidas junto com ele, ficam embutidas (array `modalidades`).
- **Interesses embutidos no usuário.** O interesse pertence a quem o demonstrou
  e é sempre lido junto com o usuário ("quais livros esse usuário quer?"). A
  lista de interesses de uma pessoa é pequena, então fica embutida (array
  `interesses` em `usuarios`), sem precisar de uma coleção separada nem de junção.
  Cada interesse guarda só a referência `livroId` ao livro desejado.
- **Referências entre usuários e livros.** `livros.proprietarioId` referencia
  `usuarios._id`, e `usuarios.interesses[].livroId` referencia `livros._id`.
  Usuários e livros mudam de forma independente, então não são duplicados um
  dentro do outro.
- **Validação de esquema** (`$jsonSchema`) nas duas coleções: o próprio banco
  rejeita documentos fora do formato (ex.: estado de conservação inválido,
  status de interesse inválido).
- **Índices:** e-mail único em `usuarios`; índice em `interesses.livroId` para
  descobrir quem se interessou por um livro; busca textual por título/autor e
  filtro por status/gênero em `livros`.
- **Trade-off conhecido.** Como os interesses ficam dentro dos usuários, a regra
  "um usuário não repete o mesmo interesse (mesmo livro e modalidade)" deve ser
  garantida pela aplicação, e não por um índice único do banco.

### Valores aceitos

| Campo | Valores |
|---|---|
| `livros.estadoConservacao` | `novo`, `ótimo`, `bom`, `regular`, `desgastado` |
| `livros.status` | `disponivel`, `reservado`, `indisponivel` |
| `livros.modalidades[].tipo` | `troca`, `venda`, `emprestimo` |
| `usuarios.interesses[].status` | `pendente`, `aceito`, `recusado` |
| `usuarios.interesses[].modalidadeDesejada` | `troca`, `venda`, `emprestimo` |

### Exemplos de documentos

**`usuarios`** (com os interesses embutidos)
```json
{
  "_id": { "$oid": "..." },
  "nome": "Carlos Eduardo Souza",
  "email": "carlos.souza@example.com",
  "cidade": "Uberlândia",
  "estado": "MG",
  "dataCadastro": { "$date": "2026-09-05T12:00:00Z" },
  "ativo": true,
  "interesses": [
    {
      "livroId": { "$oid": "<_id de livros>" },
      "modalidadeDesejada": "emprestimo",
      "mensagem": "Gostaria de ler durante as férias!",
      "status": "aceito",
      "dataCriacao": { "$date": "2026-10-30T12:00:00Z" }
    },
    {
      "livroId": { "$oid": "<_id de livros>" },
      "modalidadeDesejada": "emprestimo",
      "status": "pendente",
      "dataCriacao": { "$date": "2026-11-04T12:00:00Z" }
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
  "dataCadastro": { "$date": "2026-08-15T12:00:00Z" }
}
```

O script `scripts/criar_banco.py` insere 4 usuários, 6 livros e 5 interesses
fictícios (embutidos nos usuários). Veja o código para todos os exemplos.

## 3. Consultas (pipelines de agregação)

Duas funcionalidades foram implementadas como pipelines de agregação. Cada uma
existe em dois formatos: em Python (`scripts/consultas.py`) e em JSON
(`pipelines/`), para colar direto na aba **Aggregations** do Atlas.

### Funcionalidade 1 - Livros parados

Lista os livros **disponíveis que nunca receberam interesse**, com o nome e a
cidade do dono e há quantos dias estão anunciados. Ajuda o dono a rever
descrição ou preço.

- **Parte de:** `livros`
- **Arquivo:** `pipelines/livros_parados.json`

| Stage | O que faz |
|---|---|
| `$match` | mantém só livros com `status: "disponivel"` |
| `$lookup` | procura em `usuarios` quem tem `interesses.livroId` igual ao livro |
| `$match` | fica só com quem tem a lista de interessados vazia (`$size: 0`) |
| `$lookup` + `$unwind` | traz o dono do livro |
| `$addFields` | calcula `diasAnunciado` a partir de `dataCadastro` e `$$NOW` |
| `$project` | formata a saída |
| `$sort` | os anúncios mais antigos primeiro |

Com os dados de exemplo, o resultado é *Capitães da Areia*, único livro
disponível que ninguém demonstrou interesse.

### Funcionalidade 2 - Catálogo com filtros

Lista os livros disponíveis filtrados por **cidade do dono**, **gênero** e
**modalidade** (`troca`, `venda` ou `emprestimo`). Todos os filtros são
opcionais.

- **Parte de:** `livros`
- **Arquivo:** `pipelines/catalogo_filtros.json` (exemplo: cidade Uberlândia, modalidade troca)

| Stage | O que faz |
|---|---|
| `$match` | filtros do próprio livro (status, gênero, modalidade), antes do `$lookup` para ser mais eficiente |
| `$lookup` + `$unwind` | traz o dono do livro |
| `$match` | filtra pela cidade do dono (só existe depois do `$lookup`) |
| `$project` | formata a saída |
| `$sort` | ordem alfabética por título |

Com os dados de exemplo, o filtro Uberlândia + troca devolve *Dom Casmurro* e
*Sapiens*.


## 4. Como executar

Pré-requisitos: Python 3.9+ e um cluster no [MongoDB Atlas](https://www.mongodb.com/atlas)
(o IP da sua máquina precisa estar liberado em *Network Access*).

```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Configurar a conexão (NÃO versione o arquivo .env)
cp .env.example .env
#    edite o .env e coloque a URI do seu cluster

# 3. Criar o banco, as coleções, os índices e os documentos de exemplo
python scripts/criar_banco.py

# (opcional) apagar as coleções e recriar tudo do zero
python scripts/criar_banco.py --reset

# 4. Rodar as consultas (livros parados e catálogo com filtros)
python scripts/consultas.py
```

O script pode ser executado mais de uma vez: coleções existentes têm só a
validação atualizada e os exemplos só são inseridos em coleções vazias. Se
existir a coleção antiga `interesses` (versão anterior do projeto), use `--reset`.

## 5. Estrutura do repositório

```
trocapagina/
├── README.md              # descrição do sistema e do banco
├── requirements.txt       # dependências Python
├── .env.example           # modelo do arquivo de configuração
├── .gitignore             # ignora o .env (credenciais)
├── pipelines/
│   ├── livros_parados.json    # pipeline "Livros parados" (colar no Atlas)
│   └── catalogo_filtros.json  # pipeline "Catálogo com filtros" (colar no Atlas)
└── scripts/
    ├── criar_banco.py     # cria banco, coleções, índices e exemplos
    └── consultas.py       # executa as duas consultas em Python
```

## 6. Segurança

A URI de conexão (com usuário e senha) fica **apenas** no arquivo `.env`, que
está no `.gitignore`. Nunca coloque a senha diretamente no código nem em commits.
Todos os dados de exemplo são fictícios.
