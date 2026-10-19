# Vídeo 2: MCP do Grafana conectado no Claude

Esse é o lab do vídeo 2. Aqui a gente sobe a stack de observabilidade num Kubernetes local, sobe o MCP do Grafana e conecta tudo no Claude. No final você conversa com o Claude e ele consulta métricas, logs e traces de verdade, direto do seu Grafana.

Sem n8n e sem orquestração nesse vídeo. É só a stack, o MCP e o Claude.

Todas as telemetrias são geradas por uma aplicação de demonstração, então não precisa de nada em nuvem.

```
Claude (Code ou Desktop)
        |
        |  MCP (SSE ou stdio)
        v
   mcp-grafana  (somente leitura)
        |
        |  API do Grafana (service account Viewer)
        v
+----------------------- kind: obs-mcp-lab -----------------------+
|  Grafana + Prometheus + Loki + Tempo  (grafana/otel-lgtm)        |
|        ^                                                         |
|        | OTLP (métricas, logs e traces)                          |
|  checkout-service  <----  load-generator                         |
+------------------------------------------------------------------+
```

## O que sobe

1. Um cluster kind chamado `obs-mcp-lab`.
2. A stack `grafana/otel-lgtm` (Grafana, Prometheus, Loki e Tempo numa imagem só).
3. Uma app Flask chamada `checkout-service`, instrumentada com OpenTelemetry. Ela simula pagamentos lentos (cerca de 20%) e falhas (cerca de 10%).
4. Um gerador de carga, para sempre ter dado novo.
5. O `mcp-grafana`, com só as ferramentas de Prometheus, Loki, Tempo e datasource, em modo somente leitura.

## Pré-requisitos de ambiente

Testei em Linux. Em Mac e Windows com WSL2 deve funcionar, mas não validei.

| Item | Versão testada | Observação |
|---|---|---|
| Linux | Ubuntu recente | x86_64 |
| RAM livre | 4 GB ou mais | cluster e LGTM rodam juntos |
| Disco livre | 5 GB ou mais | imagens e volumes |
| Docker | 29.x | seu usuário precisa estar no grupo `docker` |
| Docker Compose | v2 (plugin) | o `docker-compose` v1 quebra com Docker novo |
| kind | 0.2x | cria o cluster |
| kubectl | compatível com o cluster | |
| Claude | Claude Code ou Claude Desktop | qualquer um dos dois serve |
| Node.js | só se for usar o Claude Code | para instalar o CLI |

Portas livres no host:

| Porta | Quem usa |
|---|---|
| 3000 | Grafana |
| 4317 | OTLP gRPC do LGTM |
| 18080 | checkout-service (uso 18080 porque a 8080 costuma estar ocupada) |
| 8000 | mcp-grafana (SSE) |

### Conferindo o ambiente

```bash
docker version
docker compose version
kind version
kubectl version --client
docker ps
```

Se o `docker ps` pedir permissão:

```bash
sudo usermod -aG docker $USER
newgrp docker
```

Se `docker compose version` não existir, você está só com o v1. Instale o plugin v2:

```bash
mkdir -p ~/.docker/cli-plugins
curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 -o ~/.docker/cli-plugins/docker-compose
chmod +x ~/.docker/cli-plugins/docker-compose
```

Se você não tem o kind:

```bash
curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.24.0/kind-linux-amd64
chmod +x ./kind && sudo mv ./kind /usr/local/bin/kind
```

Um aviso importante: se a sua máquina também tem k3s ou Rancher, a variável `KUBECONFIG` pode estar apontando para `/etc/rancher/k3s/k3s.yaml`, e aí o kubectl falha por falta de permissão. O `setup.sh` já força o kubeconfig do seu usuário, mas nos comandos manuais faça o mesmo:

```bash
export KUBECONFIG="$HOME/.kube/config"
```

## Passo a passo

### 1. Clone e entre na pasta

```bash
git clone https://github.com/Larasxavier/labs-mcp.git
cd labs-mcp/video-2-mcp-grafana
```

### 2. Suba o cluster e a stack

```bash
./scripts/setup.sh
```

O script cria o cluster, aplica o LGTM, builda a imagem do `checkout-service`, carrega no kind e sobe a app com o gerador de carga. Leva alguns minutos na primeira vez.

```bash
kubectl -n observability get pods
```

Os três pods (`lgtm`, `checkout-service` e `load-generator`) precisam estar `Running`.

### 3. Veja a telemetria no Grafana

Acesse `http://127.0.0.1:3000` com `admin` e `admin`. Use 127.0.0.1 mesmo, não localhost. Se você já fez port-forward como root em algum momento, pode ter um Grafana fantasma respondendo na 3000, e uma aba anônima ajuda a tirar a dúvida.

Em Explore, confira:

- Prometheus: `checkout_requests_total`
- Loki: `{service_name="checkout-service"}`
- Tempo: busca por `service.name = checkout-service`

Se os três mostram dados, a parte de telemetria está pronta. Os dados ficam num volume, então sobrevivem a reinício do pod.

### 4. Crie o service account do Grafana

O MCP precisa de um token para ler o Grafana. Siga o [guia do service account](docs/grafana-service-account.md) e crie um com a role **Viewer**, não Admin. Depois:

```bash
export GRAFANA_SERVICE_ACCOUNT_TOKEN="glsa_cole_o_seu_token_aqui"
```

O token aparece uma vez só, né. Guarde.

### 5. Suba o mcp-grafana

```bash
docker compose up -d
docker logs mcp-grafana --tail 20
```

Ele sobe em modo SSE na porta 8000, com `--disable-write` e só as ferramentas `prometheus`, `loki`, `proxied` (que é o Tempo) e `datasource`. Segundo cinto de segurança, além da role Viewer.

### 6. Conecte no Claude

Escolha um dos dois caminhos.

**Opção A: Claude Code**

```bash
claude mcp add --transport sse grafana http://localhost:8000/sse
claude mcp list
```

Abra o `claude` e use `/mcp` para ver o servidor `grafana` conectado.

**Opção B: Claude Desktop**

Aqui o Claude Desktop sobe o MCP sozinho via Docker (stdio), então nem precisa do passo 5. Edite o arquivo de configuração (Settings, Developer, Edit Config) e adicione:

```json
{
  "mcpServers": {
    "grafana": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "--add-host", "host.docker.internal:host-gateway",
        "-e", "GRAFANA_URL=http://host.docker.internal:3000",
        "-e", "GRAFANA_SERVICE_ACCOUNT_TOKEN=glsa_cole_o_seu_token_aqui",
        "grafana/mcp-grafana",
        "-t", "stdio",
        "--enabled-tools", "prometheus,loki,proxied,datasource",
        "--disable-write"
      ]
    }
  }
}
```

Reinicie o Claude Desktop. O ícone de ferramentas deve mostrar o `grafana`.

### 7. Converse com o Claude

Comece simples e vá apertando:

1. "Quais datasources existem no meu Grafana?"
2. "Qual o p95 de payment_processing_duration_seconds do checkout-service nos últimos 15 minutos?"
3. "Mostra os logs de erro do checkout-service na última hora e agrupa por tipo."
4. "Pega um trace lento do checkout-service e me diz onde está o gargalo."
5. "Com base em métricas, logs e traces, o checkout-service tem algum problema? Qual a hipótese mais provável?"

Repare que o label `job` e o `service_name` são `checkout-service`. Se o Claude errar o nome, é um bom momento para mostrar como ele usa `list_datasources` e as ferramentas de descoberta de labels para se corrigir.

## O que observar

- O MCP só lê. Role Viewer no token e `--disable-write` no servidor.
- Só 4 grupos de ferramentas habilitados, em vez do cardápio inteiro do Grafana. Menos ferramentas, menos contexto gasto.
- O guardrail de custo de query do Loki está em modo `shadow` (só registra). Troque para `enforce` no `docker-compose.yml` se quiser ver o bloqueio de verdade.
- O próprio `mcp-grafana` exporta telemetria para o LGTM, então dá para observar o agente que está fazendo observabilidade.

## Problemas que eu já encontrei

| Sintoma | Causa | Solução |
|---|---|---|
| `kind: command not found` | kind não instalado | instale conforme os pré-requisitos |
| `permission denied` no Docker | usuário fora do grupo | `usermod -aG docker` e `newgrp docker` |
| kubectl com erro de permissão em `k3s.yaml` | KUBECONFIG do k3s | `export KUBECONFIG=$HOME/.kube/config` |
| Pod `checkout-service` em CrashLoopBackOff com `pkg_resources` | setuptools novo demais | já fixado em `setuptools<81` no `requirements.txt`, rebuilde a imagem |
| `docker compose` não existe ou `KeyError: ContainerConfig` | Compose v1 | instale o plugin v2 |
| Porta já em uso ao criar o cluster | 8080 ocupada | já usamos 18080 no `kind-config.yaml` |
| Falha ao recriar o cluster, rede `kind` ausente | rede removida | `kind delete cluster --name obs-mcp-lab`, `docker network rm kind` e rode o setup de novo |
| Grafana sem dados ou com login estranho | Grafana fantasma de port-forward antigo | use `http://127.0.0.1:3000` numa aba anônima e mate port-forwards antigos |
| Logs não aparecem no Loki | app sem exportador OTLP de logs | já incluído no `app.py` desta versão |
| Grafana perde dados ao reiniciar o pod | sem volume | o manifesto já tem PVC em `/data` |
| Claude Desktop não mostra o `grafana` | JSON inválido ou Docker sem permissão | valide o JSON e rode `docker run hello-world` com o seu usuário |
| Erro 401 ou 403 do Grafana nas ferramentas | token errado ou expirado | gere outro no service account |

## Voltando ao lab depois de um tempo parado

Se você ficou dias sem usar e o MCP caiu:

```bash
export KUBECONFIG="$HOME/.kube/config"
docker start obs-mcp-lab-control-plane
kind export kubeconfig --name obs-mcp-lab
kubectl -n observability get pods
export GRAFANA_SERVICE_ACCOUNT_TOKEN="glsa_seu_token"
docker compose up -d --force-recreate
```

Se o token se perdeu, crie outro no Grafana.

## Limpeza

```bash
docker compose down
kind delete cluster --name obs-mcp-lab
```

## Estrutura da pasta

```
video-2-mcp-grafana/
  README.md
  kind-config.yaml
  docker-compose.yml    mcp-grafana em modo SSE
  app/                  app Flask instrumentada com OpenTelemetry
  k8s/                  namespace, LGTM, checkout-service e gerador de carga
  scripts/setup.sh      sobe cluster, stack e app
  docs/                 guia do service account
```

## Trade-offs

Esse lab é de demonstração. Não use como está em produção: o MCP em SSE está sem autenticação, o Grafana usa credenciais padrão e o cluster tem um nó só. A ideia é você entender o padrão (MCP somente leitura, poucas ferramentas, token Viewer) e adaptar ao seu ambiente.
