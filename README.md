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
| **Interesse** | Manifestação de interesse de um usuário em um livro, para uma modalidade específica. |

## 2. Banco de dados (MongoDB Atlas)

- **Banco:** `trocapagina`
- **Coleções:** `usuarios`, `livros`, `interesses`

### Decisões de modelagem

- **Modalidades embutidas no livro.** Um livro pode ser ofertado de mais de um
  jeito (ex.: troca *e* venda). Como as modalidades só fazem sentido dentro do
  livro e são sempre lidas junto com ele, ficam embutidas (array `modalidades`).
- **Referências para usuários.** `livros.proprietarioId` e
  `interesses.usuarioInteressadoId` referenciam `usuarios._id`; `interesses.livroId`
  referencia `livros._id`. Usuários e livros mudam de forma independente, então
  não são duplicados dentro de outros documentos.
- **Interesses em coleção própria.** Um livro popular pode receber muitos
  interesses; manter em coleção separada evita documentos que crescem sem limite.
- **Validação de esquema** (`$jsonSchema`) em todas as coleções: o próprio banco
  rejeita documentos fora do formato (ex.: estado de conservação inválido).
- **Índices:** e-mail único em `usuarios`; busca textual por título/autor e
  filtro por status/gênero em `livros`; e um interesse único por
  (livro, usuário, modalidade) em `interesses`.

### Valores aceitos

| Campo | Valores |
|---|---|
| `livros.estadoConservacao` | `novo`, `ótimo`, `bom`, `regular`, `desgastado` |
| `livros.status` | `disponivel`, `reservado`, `indisponivel` |
| `livros.modalidades[].tipo` | `troca`, `venda`, `emprestimo` |
| `interesses.status` | `pendente`, `aceito`, `recusado` |

### Exemplos de documentos

**`usuarios`**
```json
{
  "_id": { "$oid": "..." },
  "nome": "Ana Beatriz Lima",
  "email": "ana.lima@example.com",
  "cidade": "Uberlândia",
  "estado": "MG",
  "dataCadastro": { "$date": "2026-08-05T12:00:00Z" },
  "ativo": true
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

**`interesses`**
```json
{
  "_id": { "$oid": "..." },
  "livroId": { "$oid": "<_id de livros>" },
  "usuarioInteressadoId": { "$oid": "<_id de usuarios>" },
  "modalidadeDesejada": "emprestimo",
  "mensagem": "Gostaria de ler durante as férias!",
  "status": "aceito",
  "dataCriacao": { "$date": "2026-10-28T12:00:00Z" }
}
```

O script `scripts/criar_banco.py` insere 4 usuários, 6 livros e 4 interesses
fictícios (veja o código para todos os exemplos).

## 3. Como executar

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

# (opcional) apagar as 3 coleções e recriar tudo do zero
python scripts/criar_banco.py --reset
```

O script pode ser executado mais de uma vez: coleções existentes têm só a
validação atualizada e os exemplos só são inseridos em coleções vazias.

## 4. Estrutura do repositório

```
trocapagina/
├── README.md              # descrição do sistema e do banco
├── requirements.txt       # dependências Python
├── .env.example           # modelo do arquivo de configuração
├── .gitignore             # ignora o .env (credenciais)
└── scripts/
    └── criar_banco.py     # cria banco, coleções, índices e exemplos
```

## 5. Segurança

A URI de conexão (com usuário e senha) fica **apenas** no arquivo `.env`, que
está no `.gitignore`. Nunca coloque a senha diretamente no código nem em commits.
Todos os dados de exemplo são fictícios.
