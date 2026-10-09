# Vendas atribuídas ao criador

Webhook simplificado inspirado em pedidos Shopify; não usa uma loja real.
Os valores são **centavos inteiros em BRL**. `POST /orders` recebe eventos
`status: "paid"`; estornos entram em `POST /refunds`. IDs são escopados por loja.

A regra única em `attribution()` é: **cupom conhecido vence UTM conhecida**;
sem cupom conhecido, UTM conhecida vence; sem ambos, não atribui. Cada pedido
fixa sua atribuição no primeiro recebimento, a no máximo um criador. Adicionar
um cupom depois não reatribui vendas antigas.

Pedido repetido é idempotente. Estorno deduplica por loja + ID do estorno,
permite parcial e acumula no máximo o total da venda. Excesso é preservado como
`excess_cents`, sem criar saldo negativo. Estorno anterior ao pedido fica
`pending` persistido; quando o pedido chega, todos são aplicados na ordem de
recebimento. Reuso de ID com payload diferente retorna 409. O ledger conserva
venda e reversões; nada é apagado.

## Exemplo

```bash
curl -s "$BASE/creators" -H 'Content-Type: application/json' -d '{"shop":"demo","id":"alice","coupon":"ALICE"}'
curl -s "$BASE/creators" -H 'Content-Type: application/json' -d '{"shop":"demo","id":"bob","coupon":"BOB"}'
curl -s "$BASE/refunds" -H 'Content-Type: application/json' -d '{"shop":"demo","id":"r1","order_id":"o1","amount_cents":3000}'
curl -s "$BASE/orders" -H 'Content-Type: application/json' -d '{"shop":"demo","id":"o1","total_cents":10000,"coupon":"ALICE","utm_creator":"bob","status":"paid"}'
curl -s "$BASE/orders/demo/o1"
```

O estorno inicial retorna `state: "pending"`. Ao receber o pedido, a resposta
tem `attribution.creator_id: "alice"`, `refunded_cents: 3000`, `net_cents: 7000`,
`attributed_cents: 7000` e ledger `[+10000, -3000]`. Repetir qualquer evento não
altera o saldo. `GET /refunds/demo/r1` mostra o recibo aplicado.

Com mais tempo: validação HMAC Shopify sobre corpo bruto, adapter do payload
completo, moedas diferentes, pedidos editados e eventos de cancelamento. Esses
contratos não são fingidos aqui; `API_TOKEN` protege apenas o demo simplificado.

## Rodar e verificar

Python 3.12 com base de fusos IANA (incluída no Ubuntu); sem `pip install`.

```bash
python3 -m unittest -v
python3 app.py
```

API na porta 8080. `PORT`, `HOST` (padrão 127.0.0.1), `DATABASE_PATH` (padrão
`data.sqlite3`) e `API_TOKEN` configuram o processo. Com `API_TOKEN`, envie
`Authorization: Bearer ...`; `/health` fica público. Os exemplos abaixo usam
`BASE` como a URL do processo ou de um proxy HTTPS. `test_http.py` executa o
fluxo pela rede HTTP real, além dos testes de domínio com relógio controlado.

Respostas são JSON; sucesso 200, entrada inválida 422, conflito 409, ausente
404. JSON malformado retorna 400. SQLite persiste estado em transações
`BEGIN IMMEDIATE`; uma operação inválida faz rollback, inclusive de alterações
parciais. Reiniciar preserva dados. Cada execução de testes usa banco isolado.

## Limites desta entrega

O adaptador HTTP é uma demonstração síncrona, não um servidor de produção.
SQLite guarda um documento de estado por aplicação: simples para verificar as
invariantes e a persistência, mas inadequado para grande volume. Com mais tempo,
normalizaria tabelas e índices, adicionaria autenticação por usuário/tenant,
limites operacionais, observabilidade e migrações. O token compartilhado não
substitui autorização por recurso. Não exponha dados reais neste demo.

## Uso de IA

Codex implementou, testou e fez revisão automatizada das regras, exemplos e
resultados a pedido de Leon Hatori. Não declaramos revisão humana que ainda
não ocorreu. Detalhes em [AI_USAGE.md](AI_USAGE.md).
