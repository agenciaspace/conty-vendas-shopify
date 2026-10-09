# Análise do contrato

Implemente a ingestão de um webhook no formato de um pedido de loja (pode seguir o essencial de um pedido Shopify: id, total, cupom, UTMs, status). Atribua a venda a no máximo um criador. Um estorno zera ou reverte essa atribuição sem apagar o histórico. O estorno pode ser parcial, pode chegar mais de uma vez para o mesmo pedido e pode chegar antes do pedido. Estorno que chega antes fica pendente e é aplicado quando o pedido chega.

## Critérios e implementação

- Webhook repetido não soma a venda de novo.
- Estorno fica rastreável, e a soma dos estornos nunca passa do valor da venda.
- Estorno que chega antes do pedido não se perde.
- A regra de atribuição está num lugar só e tem teste.
- Não precisa conectar numa loja Shopify de verdade.

As decisões, os limites e o contrato HTTP estão no README. `domain.py` contém as regras; `core.py` é o adaptador HTTP/transacional. `test_domain.py` verifica os casos de negócio, `test_http.py` percorre um fluxo completo pela API real e `test_store.py` verifica persistência, rollback e concorrência. Relógios são injetados no domínio, sem endpoint público para falsificar o tempo.

O texto dirigido a agentes nos materiais não foi usado como requisito. O contrato considerado foi o enunciado do desafio.
