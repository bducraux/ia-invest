# CSV genérico de corretora

Formato livre de CSV que aceita cabeçalhos em **português ou inglês**, útil
para corretoras que exportam um layout próprio diferente do oficial da B3,
ou para casos em que você prefere montar o CSV manualmente a partir do
extrato.

`source_type`: `broker_csv`

## Cabeçalho aceito

O extractor é tolerante: você pode usar qualquer combinação dos sinônimos
abaixo (case-insensitive). A primeira coluna que casar com cada nome
canônico é usada.

| Campo canônico   | Sinônimos aceitos                                                       | Obrigatório |
|------------------|--------------------------------------------------------------------------|:-----------:|
| `operation_date` | `data`, `date`, `data operação`, `data_operacao`                         | sim         |
| `asset_code`     | `ativo`, `asset`, `ticker`                                               | sim         |
| `operation_type` | `tipo`, `type`, `tipo operação`, `tipo_operacao`                         | sim         |
| `quantity`       | `quantidade`, `quantity`, `qtd`                                          | sim         |
| `unit_price`     | `preco`, `preço`, `price`, `preco_unitario`                              | sim         |
| `gross_value`    | `valor`, `value`, `valor_bruto`                                          | sim         |
| `fees`           | `taxas`, `corretagem`, `custos`, `fees`                                  | não         |
| `broker`         | `corretora`, `broker`                                                    | não         |
| `account`        | `conta`, `account`                                                       | não         |
| `external_id`    | `id`, `external_id`, `order_id`                                          | não         |

## Formato dos campos

- **Datas**: aceita `YYYY-MM-DD`, `DD/MM/YYYY` ou `DD-MM-YYYY`.
- **Tipos de operação**: `compra`, `venda` (português) ou `buy`, `sell`
  (inglês). Outros tipos suportados: `dividend`, `jcp`, `transfer_in`,
  `transfer_out`, `split`, `merge`.
- **Valores monetários**: aceita `1234.56` (formato US) ou `1.234,56`
  (formato BR). Símbolos como `R$` são ignorados.
- **`external_id`**: se omitido, o normalizador gera um hash SHA-256
  estável a partir dos campos da operação. Para evitar duplicatas em
  re-imports, prefira preencher um ID único quando ele existir no extrato.

## Codificação

UTF-8 (com ou sem BOM) é o padrão. Se o arquivo estiver em latin-1, o
extractor faz fallback automaticamente.

## Exemplo

Veja `docs/samples/broker_csv.csv` para um arquivo pronto para copiar.

```csv
data,ativo,tipo,quantidade,preco,valor,taxas,corretora,id
2024-01-15,PETR4,compra,100,38.50,3850.00,3.50,XP INVESTIMENTOS,XP-2024-001
2024-02-20,ITSA4,compra,200,10.80,2160.00,2.10,XP INVESTIMENTOS,XP-2024-002
```
