# Previdência — Fundação IBM

Extrato mensal em PDF da Fundação Previdenciária IBM. Cobre planos PGBL e
VGBL administrados pela Fundação. Atualmente é a **única fonte de
previdência suportada** porque é a única à qual temos acesso.

`source_type`: `previdencia_ibm_pdf`

## Como baixar o extrato

1. Acesse o portal da participante da Fundação IBM
   (<https://www.fundacaoibm.com.br/>).
2. Faça login com o seu CPF e senha.
3. Vá em **Extratos → Extrato Mensal**.
4. Selecione o mês desejado e clique em **Visualizar/Baixar**.
5. Salve o PDF em `portfolios/<sua-carteira-previdencia>/inbox/`.

Não é necessário renomear o arquivo — o extractor identifica
automaticamente PDFs da Fundação IBM pelo cabeçalho do documento.

## Política de cobertura

O extrato mensal traz uma **fotografia da posição** ao final do período,
**não** uma lista de movimentações. O IA-Invest persiste apenas o snapshot
mais recente por (carteira, ativo) na tabela `previdencia_snapshots` —
imports antigos são silenciosamente ignorados se já houver um snapshot
mais novo.

Para um histórico completo, basta dropar todos os PDFs juntos no `inbox/`
e rodar `make import-all`. O extractor escolhe o mais recente
automaticamente.

## Campos extraídos

Para cada plano (linha) presente no extrato:

- Nome do produto
- Quantidade de cotas
- Preço unitário (cotas x BRL)
- Valor de mercado total
- Mês de referência (`YYYY-MM`)
- Datas de início e fim do período

## Adicionando suporte a outros planos

Outros provedores de previdência (Brasilprev, Itaú Vida e Previdência,
Caixa, etc.) ainda **não** têm extractors. Para contribuir:

1. Crie um novo arquivo em `extractors/`, por exemplo
   `previdencia_brasilprev_pdf.py`.
2. Implemente uma classe que herda de `BaseExtractor` com
   `can_handle()` e `extract()`. Use `previdencia_ibm_pdf.py` como
   referência.
3. Registre no `_REGISTRY` de `extractors/__init__.py`.
4. Adicione o tipo na lista `sources` do `portfolio.yml` da carteira.
5. Crie testes em `tests/test_extractors/` com pelo menos um PDF
   anonimizado de fixture.

Pull requests são bem-vindos.
