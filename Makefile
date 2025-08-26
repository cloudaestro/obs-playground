.PHONY: help bootstrap deploy break heal port-forward logs clean
.DEFAULT_GOAL := help

CLUSTER_NAME := hrt-demo
NAMESPACE := hrt-sre
PORTAL_NAMESPACE := portal
GRAFANA_PORT := 3000
PROMETHEUS_PORT := 9090
PORTAL_PORT := 8080

help: ## Show this help message
	@echo "SRE Playground - Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

bootstrap: ## Create k3d cluster and deploy all components
	@echo "Bootstrapping SRE playground..."
	./scripts/bootstrap.sh

deploy: ## Deploy all applications to existing cluster
	@echo "Deploying applications..."
	kubectl apply -k k8s/overlays/dev

break: ## Introduce failures for demo (restart portal deployment repeatedly)
	@echo "Breaking things for demo..."
	kubectl -n $(PORTAL_NAMESPACE) delete pod -l app=portal --force --grace-period=0
	kubectl -n $(PORTAL_NAMESPACE) patch deployment portal -p '{"spec":{"template":{"spec":{"containers":[{"name":"portal","env":[{"name":"FAILURE_RATE","value":"1.0"}]}]}}}}'

heal: ## Trigger auto-healer manually
	@echo "Triggering auto-healer..."
	kubectl -n $(NAMESPACE) create job --from=cronjob/auto-healer auto-healer-manual-$$(date +%s)

port-forward: ## Start port forwarding for services
	@echo "Starting port forwarding..."
	@echo "Grafana: http://localhost:$(GRAFANA_PORT) (admin/admin)"
	@echo "Prometheus: http://localhost:$(PROMETHEUS_PORT)"
	@echo "Portal: http://localhost:$(PORTAL_PORT)"
	@kubectl -n $(NAMESPACE) port-forward svc/grafana $(GRAFANA_PORT):3000 &
	@kubectl -n $(NAMESPACE) port-forward svc/prometheus $(PROMETHEUS_PORT):9090 &
	@kubectl -n $(PORTAL_NAMESPACE) port-forward svc/portal $(PORTAL_PORT):80 &
	@echo "Port forwarding started. Press Ctrl+C to stop all."
	@wait

logs: ## Show logs for all components
	@echo "=== Portal Logs ==="
	kubectl -n $(PORTAL_NAMESPACE) logs -l app=portal --tail=20
	@echo ""
	@echo "=== Auto-healer Logs ==="
	kubectl -n $(NAMESPACE) logs -l app=auto-healer --tail=20
	@echo ""
	@echo "=== Batch-sync Logs ==="
	kubectl -n $(NAMESPACE) logs -l app=batch-sync --tail=20
	@echo ""
	@echo "=== Mock-Slack Logs ==="
	kubectl -n $(NAMESPACE) logs -l app=mock-slack --tail=10

clean: ## Delete k3d cluster
	@echo "Cleaning up cluster..."
	k3d cluster delete $(CLUSTER_NAME) || true

tf-init: ## Initialize Terraform
	cd terraform && terraform init

tf-plan: ## Run Terraform plan
	cd terraform && terraform plan -no-color

tf-fmt: ## Format Terraform files
	cd terraform && terraform fmt -recursive

tf-validate: ## Validate Terraform configuration
	cd terraform && terraform validate

build-images: ## Build all Docker images
	@echo "Building Docker images..."
	docker build -t hrt-portal:latest apps/portal/
	docker build -t hrt-batch-sync:latest apps/batch-sync/
	docker build -t hrt-auto-healer:latest apps/auto-healer/
	docker build -t hrt-mock-slack:latest apps/mock-slack/

load-images: ## Load images into k3d cluster
	@echo "Loading images into k3d..."
	k3d image import hrt-portal:latest -c $(CLUSTER_NAME)
	k3d image import hrt-batch-sync:latest -c $(CLUSTER_NAME)
	k3d image import hrt-auto-healer:latest -c $(CLUSTER_NAME)
	k3d image import hrt-mock-slack:latest -c $(CLUSTER_NAME)