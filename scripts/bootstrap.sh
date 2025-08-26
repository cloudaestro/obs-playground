#!/bin/bash
set -euo pipefail

CLUSTER_NAME="hrt-demo"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1"
}

success() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] SUCCESS:${NC} $1"
}

check_prerequisites() {
    log "Checking prerequisites..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        error "Docker is not running. Please start Docker first."
        exit 1
    fi
    
    success "Docker is available and running"
    
    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        error "kubectl is not installed. Please install kubectl first."
        exit 1
    fi
    
    success "kubectl is available"
    
    # Install k3d if not available
    if ! command -v k3d &> /dev/null; then
        warn "k3d not found, installing..."
        if [[ "$OSTYPE" == "darwin"* ]]; then
            brew install k3d
        elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
            curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | bash
        else
            error "Unsupported OS for automatic k3d installation. Please install k3d manually."
            exit 1
        fi
    fi
    
    success "k3d is available"
}

create_cluster() {
    log "Creating k3d cluster '$CLUSTER_NAME'..."
    
    # Delete existing cluster if it exists
    if k3d cluster list | grep -q "$CLUSTER_NAME"; then
        warn "Cluster '$CLUSTER_NAME' already exists, deleting..."
        k3d cluster delete "$CLUSTER_NAME"
    fi
    
    # Create new cluster
    k3d cluster create "$CLUSTER_NAME" \
        --agents 2 \
        --port "8080:80@loadbalancer" \
        --port "3000:3000@loadbalancer" \
        --port "9090:9090@loadbalancer" \
        --port "9093:9093@loadbalancer" \
        --wait
    
    # Set kubectl context
    kubectl config use-context "k3d-$CLUSTER_NAME"
    
    success "Cluster '$CLUSTER_NAME' created successfully"
}

build_images() {
    log "Building Docker images..."
    
    cd "$PROJECT_ROOT"
    
    # Build all application images
    docker build -t hrt-portal:latest apps/portal/
    docker build -t hrt-batch-sync:latest apps/batch-sync/
    docker build -t hrt-auto-healer:latest apps/auto-healer/
    docker build -t hrt-mock-slack:latest apps/mock-slack/
    
    success "All Docker images built successfully"
}

load_images() {
    log "Loading images into k3d cluster..."
    
    k3d image import hrt-portal:latest -c "$CLUSTER_NAME"
    k3d image import hrt-batch-sync:latest -c "$CLUSTER_NAME"
    k3d image import hrt-auto-healer:latest -c "$CLUSTER_NAME"
    k3d image import hrt-mock-slack:latest -c "$CLUSTER_NAME"
    
    success "All images loaded into cluster"
}

deploy_base_manifests() {
    log "Applying base Kubernetes manifests..."
    
    cd "$PROJECT_ROOT"
    kubectl apply -k k8s/base
    
    # Wait for namespaces to be ready
    kubectl wait --for=condition=Active --timeout=60s namespace/hrt-sre
    kubectl wait --for=condition=Active --timeout=60s namespace/portal
    
    success "Base manifests applied successfully"
}

deploy_monitoring() {
    log "Deploying monitoring stack..."
    
    cd "$PROJECT_ROOT"
    kubectl apply -k k8s/overlays/dev
    
    # Wait for monitoring components to be ready
    log "Waiting for Prometheus to be ready..."
    kubectl -n hrt-sre wait --for=condition=available --timeout=300s deployment/prometheus
    
    log "Waiting for Grafana to be ready..."
    kubectl -n hrt-sre wait --for=condition=available --timeout=300s deployment/grafana
    
    log "Waiting for Alertmanager to be ready..."
    kubectl -n hrt-sre wait --for=condition=available --timeout=300s deployment/alertmanager
    
    success "Monitoring stack deployed successfully"
}

deploy_applications() {
    log "Deploying applications..."
    
    # Wait for portal to be ready
    log "Waiting for Portal to be ready..."
    kubectl -n portal wait --for=condition=available --timeout=300s deployment/portal
    
    # Wait for mock-slack to be ready
    log "Waiting for Mock-Slack to be ready..."
    kubectl -n hrt-sre wait --for=condition=available --timeout=300s deployment/mock-slack
    
    success "Applications deployed successfully"
}

verify_deployment() {
    log "Verifying deployment..."
    
    # Check pod status
    echo ""
    log "Pod status in hrt-sre namespace:"
    kubectl -n hrt-sre get pods
    
    echo ""
    log "Pod status in portal namespace:"
    kubectl -n portal get pods
    
    echo ""
    log "Service status:"
    kubectl -n hrt-sre get svc
    kubectl -n portal get svc
    
    # Check if services are responsive
    log "Testing service health..."
    
    # Port forward temporarily to test services
    kubectl -n portal port-forward svc/portal 8080:80 &
    PORTAL_PID=$!
    
    sleep 5
    
    if curl -f http://localhost:8080/health > /dev/null 2>&1; then
        success "Portal service is healthy"
    else
        warn "Portal service health check failed"
    fi
    
    kill $PORTAL_PID 2>/dev/null || true
    
    success "Deployment verification completed"
}

setup_gitops() {
    log "Setting up GitOps (optional)..."
    
    if command -v argocd &> /dev/null; then
        log "Argo CD CLI found, setting up Argo CD applications..."
        kubectl apply -f argo/project.yaml
        kubectl apply -f argo/app-of-apps.yaml
        success "Argo CD applications configured"
    else
        log "Argo CD not found, GitOps watcher available as alternative"
        log "To use GitOps watcher: python3 gitops/gitops-watcher.py"
    fi
}

print_access_info() {
    echo ""
    success "🎉 Bootstrap completed successfully!"
    echo ""
    log "Access Information:"
    echo "  📊 Grafana:     http://localhost:3000 (admin/admin)"
    echo "  📈 Prometheus:  http://localhost:9090"
    echo "  🔔 Alertmanager: http://localhost:9093"
    echo "  🌐 Portal:      http://localhost:8080"
    echo "  💬 Mock Slack:  http://localhost:8080/webhook (for alerts)"
    echo ""
    log "Next steps:"
    echo "  1. Run 'make port-forward' to start port forwarding"
    echo "  2. Run 'make break' to introduce failures for demo"
    echo "  3. Run 'make heal' to trigger auto-healer manually"
    echo "  4. Run 'make logs' to view application logs"
    echo ""
    log "Cluster: k3d-$CLUSTER_NAME"
    log "To delete: k3d cluster delete $CLUSTER_NAME"
}

# Main execution
main() {
    log "Starting SRE Playground bootstrap..."
    
    check_prerequisites
    create_cluster
    build_images
    load_images
    deploy_base_manifests
    deploy_monitoring
    deploy_applications
    verify_deployment
    setup_gitops
    print_access_info
    
    success "Bootstrap process completed! 🚀"
}

# Handle script interruption
trap 'error "Bootstrap interrupted!"; exit 1' INT TERM

# Run main function
main "$@"