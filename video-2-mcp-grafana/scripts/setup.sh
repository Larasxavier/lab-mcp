#!/usr/bin/env bash
# Sobe o lab completo: cluster kind, stack de observabilidade, app instrumentada
# e o gerador de carga. O docker-compose (mcp-grafana) fica de fora daqui
# de proposito, porque ele depende do token do Grafana (ver docs/grafana-service-account.md).
set -euo pipefail

# Se a maquina tambem tiver Rancher/k3s instalado, a variavel KUBECONFIG do
# shell pode estar apontando pra /etc/rancher/k3s/k3s.yaml (sem permissao de
# leitura pro usuario comum), o que faz o kubectl falhar mesmo com o cluster
# do kind criado certinho. Forcamos aqui o kubeconfig padrao do usuario, onde
# o kind escreve o cluster obs-mcp-lab.
export KUBECONFIG="$HOME/.kube/config"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "==> [1/5] Criando cluster kind (obs-mcp-lab)"
if kind get clusters 2>/dev/null | grep -q "^obs-mcp-lab$"; then
  echo "cluster obs-mcp-lab ja existe, pulando"
else
  kind create cluster --config kind-config.yaml
fi

echo "==> [2/5] Aplicando namespace e stack LGTM"
kubectl apply -f k8s/00-namespace.yaml
kubectl apply -f k8s/01-lgtm.yaml

echo "==> [3/5] Buildando e carregando a imagem do checkout-service"
docker build -t checkout-service:lab ./app
kind load docker-image checkout-service:lab --name obs-mcp-lab

echo "==> [4/5] Subindo checkout-service e load-generator"
kubectl apply -f k8s/02-demo-app.yaml
kubectl apply -f k8s/03-load-generator.yaml

echo "==> [5/5] Aguardando os pods ficarem prontos"
kubectl -n observability rollout status deployment/lgtm --timeout=180s
kubectl -n observability rollout status deployment/checkout-service --timeout=120s
kubectl -n observability rollout status deployment/load-generator --timeout=60s


echo
echo "Cluster pronto. Proximos passos estao no README, a partir do passo 4."
