# Fontes de dados suportadas

Cada fonte tem um extractor próprio que sabe interpretar o formato original
do arquivo (PDF, CSV ou XLSX) e converter as linhas em operações
normalizadas no banco. Os arquivos ficam na pasta `inbox/` da carteira e,
após a importação, são movidos para `processed/` (ou `rejected/` em caso
de falha).

## Tabela de fontes

| Fonte                                          | Tipo de arquivo | Carteira típica          |
|------------------------------------------------|-----------------|--------------------------|
| [B3 — Movimentação](b3-csv.md)                 | CSV ou XLSX     | `renda-variavel`         |
| [CSV genérico de corretora](broker-csv.md)     | CSV             | `renda-variavel`         |
| [Binance — Spot Trade History](binance-csv.md) | CSV             | `cripto`                 |
| [Avenue — Apex Statement](avenue-apex.md)      | PDF             | `internacional`          |
| [XLSX manual (bootstrap)](manual-xlsx.md)      | XLSX            | `renda-variavel`, `cripto` |
| [Previdência — Fundação IBM](previdencia-ibm.md)| PDF            | `previdencia`            |

Para renda fixa (CDB/LCI/LCA), o formato CSV está descrito em
[`docs/renda-fixa.md`](../renda-fixa.md).

## Adicionando uma nova fonte

Cada extractor é uma classe Python em `extractors/` que herda de
`BaseExtractor` e implementa dois métodos: `can_handle(file_path)` e
`extract(file_path)`. Para registrar o extractor, basta adicioná-lo ao
dicionário `_REGISTRY` em `extractors/__init__.py` e habilitá-lo em
`portfolio.yml` da carteira que vai usá-lo.

Pull requests adicionando suporte a novas corretoras, exchanges ou planos
de previdência são bem-vindos. O CLAUDE.md (raiz do projeto) descreve o
contrato em mais detalhes na seção *Extending the system*.
