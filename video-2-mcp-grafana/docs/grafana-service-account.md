# Gerando o token do Grafana para o mcp-grafana

O `mcp-grafana` autentica contra o Grafana usando um **service account token**
(a forma atual recomendada pelo Grafana, substituindo as antigas API keys).

## Via interface (recomendado no lab ao vivo)

1. Faça o port-forward do Grafana, se ainda não fez:
   ```bash
   kubectl -n observability port-forward svc/lgtm 3000:3000
   ```
2. Acesse `http://localhost:3000` e faça login (usuário/senha padrão da imagem
   `grafana/otel-lgtm` costuma ser `admin`/`admin`; se tiver sido alterado,
   confira com `kubectl -n observability logs deploy/lgtm | grep -i admin`).
3. Vá em **Administration > Users and access > Service accounts**.
4. Clique em **Add service account**, dê um nome (ex: `mcp-grafana-lab`) e
   selecione a role **Viewer** (leitura é suficiente e mais seguro para esse
   caso de uso, ele só precisa consultar Prometheus/Loki/Tempo).
5. Dentro do service account criado, clique em **Add service account token**,
   gere o token e copie o valor (começa com `glsa_`). Ele só aparece uma vez.
6. Exporte como variável de ambiente antes de subir o `docker-compose.yml`:
   ```bash
   export GRAFANA_SERVICE_ACCOUNT_TOKEN="glsa_xxx..."
   ```

## Via API (alternativa para automatizar em scripts)

```bash
GRAFANA_URL="http://localhost:3000"
ADMIN_USER="admin"
ADMIN_PASS="admin"

# cria o service account
SA_ID=$(curl -s -u "$ADMIN_USER:$ADMIN_PASS" -X POST "$GRAFANA_URL/api/serviceaccounts" \
  -H "Content-Type: application/json" \
  -d '{"name":"mcp-grafana-lab","role":"Viewer"}' | jq -r '.id')

# gera o token para esse service account
curl -s -u "$ADMIN_USER:$ADMIN_PASS" -X POST "$GRAFANA_URL/api/serviceaccounts/$SA_ID/tokens" \
  -H "Content-Type: application/json" \
  -d '{"name":"mcp-grafana-lab-token"}' | jq -r '.key'
```

Guarde o valor retornado, é o `GRAFANA_SERVICE_ACCOUNT_TOKEN`.

## Ponto de atenção

Não use a role **Admin** aqui. O `mcp-grafana`, além de consultar dados,
também expõe ferramentas de escrita (criar/editar dashboards e alertas,
dependendo da versão). Para o caso de uso deste lab (triagem/investigação),
a role **Viewer** já cobre tudo que o agente precisa, e reduz a superfície
caso o token vaze ou o agente seja induzido a fazer algo indevido.
