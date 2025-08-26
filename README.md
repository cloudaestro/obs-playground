# HRT SRE Playground

A comprehensive local-only SRE demonstration environment showcasing observability, auto-healing, and GitOps practices using k3d, Kubernetes, and modern SRE tooling.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        k3d Cluster (hrt-demo)                  │
│                                                                 │
│  ┌─────────────────┐    ┌──────────────────────────────────────┐ │
│  │   Portal NS     │    │              HRT-SRE NS             │ │
│  │                 │    │                                      │ │
│  │ ┌─────────────┐ │    │ ┌──────────┐  ┌──────────────────┐  │ │
│  │ │   Portal    │ │    │ │Prometheus│  │    Grafana       │  │ │
│  │ │  (FastAPI)  │◄────┤ │          │  │ (RED Metrics)    │  │ │
│  │ │             │ │    │ │          │  │ (SLO Dashboards) │  │ │
│  │ └─────────────┘ │    │ └──────────┘  └──────────────────┘  │ │
│  └─────────────────┘    │                                      │ │
│                         │ ┌──────────────┐  ┌───────────────┐  │ │
│  ┌─────────────────┐    │ │ Alertmanager │  │  Mock-Slack   │  │ │
│  │   Auto-Healer   │    │ │              │──► (Webhooks)    │  │ │
│  │   (CronJob)     │    │ │              │  │               │  │ │
│  │                 │    │ └──────────────┘  └───────────────┘  │ │
│  │ Monitors & Heals│    │                                      │ │
│  │ High Restart    │    │ ┌──────────────────────────────────┐  │ │
│  │ Count Pods      │    │ │         Batch-Sync              │  │ │
│  └─────────────────┘    │ │         (CronJob)               │  │ │
│                         │ │                                  │  │ │
│                         │ └──────────────────────────────────┘  │ │
│                         └──────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘

     External Access (Port Forwarding)
     ┌─────────────┬─────────────┬─────────────┬─────────────┐
     │ Portal      │ Grafana     │ Prometheus  │ Alerts      │
     │ :8080       │ :3000       │ :9090       │ Mock-Slack  │
     └─────────────┴─────────────┴─────────────┴─────────────┘
```

## Features

### 🔧 **Core Components**
- **FastAPI Portal**: Demo web application with configurable failure rates and Prometheus metrics
- **Batch Sync Service**: CronJob demonstrating batch processing with error handling
- **Auto-Healer**: Kubernetes-native service that automatically restarts deployments with high pod restart counts
- **Mock Slack**: Local webhook receiver for testing alerting workflows

### 📊 **Observability Stack**
- **Prometheus**: Metrics collection and alerting
- **Grafana**: RED metrics dashboards and SLO burn rate visualization
- **Alertmanager**: Alert routing and notification management
- **Custom Dashboards**: Pre-configured dashboards for portal metrics and SLO monitoring

### 🚀 **SRE Practices**
- **Service Level Objectives (SLOs)**: 99.9% availability target with burn rate alerting
- **Error Budget Management**: Automated tracking and alerting on budget consumption
- **Auto-Healing**: Proactive remediation of unhealthy workloads
- **Infrastructure as Code**: Terraform modules for configuration management

### 🔄 **GitOps & CI/CD**
- **Kustomize**: Environment-specific configuration overlays
- **Argo CD Integration**: Optional GitOps workflow (manifests provided)
- **GitOps Watcher**: Lightweight alternative to Argo CD for local development
- **GitHub Actions**: Comprehensive CI/CD pipeline with security scanning

## Quick Start (5-Minute Demo)

### Prerequisites
- Docker Desktop (running)
- kubectl
- Git

### 1. Bootstrap the Environment
```bash
git clone <this-repo>
cd hrt-sre-playground

# Run the automated setup (installs k3d if needed)
make bootstrap
```

### 2. Access the Services
```bash
# Start port forwarding (in a separate terminal)
make port-forward
```

Access points:
- **Grafana**: http://localhost:3000 (admin/admin)
- **Prometheus**: http://localhost:9090  
- **Portal**: http://localhost:8080
- **Mock Slack**: View alerts at http://localhost:8080 (webhook endpoint)

### 3. Observe Normal Operations
1. Visit **Grafana** dashboards:
   - "Portal RED Metrics" - Request rate, errors, duration
   - "SLO Burn Rate Dashboard" - Error budget and burn rate tracking
   
2. Check **Portal** health: http://localhost:8080/health

### 4. Introduce Failures & Watch Auto-Healing
```bash
# Introduce high failure rate and force pod restarts
make break

# Watch auto-healer detect and fix issues
make logs
```

Watch in Grafana:
- Error rate spikes in RED metrics
- SLO burn rate alerts trigger
- Auto-healer detects unhealthy pods and triggers deployment restart

### 5. Manual Healing & Verification
```bash
# Trigger auto-healer manually
make heal

# Verify recovery
curl http://localhost:8080/health
```

## Detailed Setup

### Manual Installation Steps

1. **Create the k3d cluster**:
```bash
k3d cluster create hrt-demo --agents 2 --port "8080:80@loadbalancer" --wait
```

2. **Build and load Docker images**:
```bash
make build-images
make load-images
```

3. **Deploy infrastructure**:
```bash
kubectl apply -k k8s/overlays/dev
```

4. **Verify deployment**:
```bash
kubectl get pods -A
```

### Configuration

#### Environment Variables
- `FAILURE_RATE`: Control portal failure simulation (0.0-1.0)
- `RESTART_THRESHOLD`: Pod restart count threshold for auto-healer (default: 3)
- `DRY_RUN`: Set auto-healer to dry-run mode (true/false)

#### Terraform Variables
```bash
cd terraform
terraform init
terraform plan -var="cluster_name=my-demo"
```

## Component Details

### Portal Application (`apps/portal/`)
- FastAPI web service with health endpoints and metrics
- Configurable failure injection for testing
- Prometheus metrics export (/metrics)
- Comprehensive error simulation

### Auto-Healer (`apps/auto-healer/`)
- Monitors pod restart counts across namespaces
- Patches deployments to trigger rolling updates
- Unit tested with kubernetes-client
- Exports healing metrics to Prometheus

### Batch-Sync (`apps/batch-sync/`)
- Simulates batch data processing workloads
- Configurable failure rates and batch sizes
- Push metrics to Prometheus pushgateway
- CronJob-based execution

### Mock-Slack (`apps/mock-slack/`)
- Receives and displays Alertmanager webhook notifications
- Web interface for viewing alert history
- Mimics Slack webhook format for testing

## Monitoring & Alerting

### Key Metrics Tracked
- **Request Rate**: Portal HTTP requests/second
- **Error Rate**: 5xx errors as percentage of total requests  
- **Response Time**: P50, P95, P99 latency percentiles
- **Availability**: Current uptime percentage
- **Error Budget**: Remaining error budget based on 99.9% SLO

### Alert Conditions
- **PortalHighErrorRate**: Error rate > 10% for 2 minutes
- **PortalHighLatency**: P95 latency > 500ms for 2 minutes
- **PortalSLOBurn**: Error budget burning too fast (14.4x normal rate)
- **PortalHighRestartRate**: Container restarts > 3 in 15 minutes

### SLO Configuration
- **Availability Target**: 99.9% (43.2 minutes downtime/month)
- **Error Budget**: 0.1% of requests can fail
- **Burn Rate Alert**: Triggers if consuming budget 14.4x faster than sustainable

## GitOps Options

### Option 1: Argo CD (Full GitOps)
```bash
# Install Argo CD
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Apply our applications
kubectl apply -f argo/project.yaml
kubectl apply -f argo/app-of-apps.yaml
```

### Option 2: GitOps Watcher (Lightweight)
```bash
# Install dependencies
pip install -r gitops/requirements.txt

# Start watcher (applies changes automatically)
python gitops/gitops-watcher.py
```

## Development & Testing

### Running Tests
```bash
# Python unit tests
cd apps/auto-healer
python -m pytest test_healer.py -v

# Terraform validation  
make tf-validate
make tf-plan
```

### Local Development
```bash
# Port forward to services
make port-forward

# View logs
make logs

# Clean up
make clean
```

## CI/CD Pipeline

The GitHub Actions workflow (`.github/workflows/ci.yml`) includes:

- **Code Quality**: Black formatting, Flake8 linting, YAML validation
- **Security**: Trivy vulnerability scanning
- **Testing**: Python unit tests, integration tests with k3d
- **Infrastructure**: Terraform validation and planning
- **Kubernetes**: Manifest validation with kubectl dry-run
- **Images**: Multi-stage Docker builds with caching

## Architecture Decisions

### Why k3d?
- Lightweight Kubernetes distribution perfect for local development
- Fast cluster creation/deletion
- Built-in load balancer and port mapping
- Minimal resource usage

### Why FastAPI for Portal?
- Modern Python web framework with automatic OpenAPI docs
- Built-in support for async operations
- Easy Prometheus metrics integration
- Comprehensive request/response modeling

### Why CronJobs for Background Services?
- Kubernetes-native job scheduling
- Built-in retry and failure handling
- Easy to monitor with standard Kubernetes tools
- Demonstrates batch workload patterns

### Why Mock Slack Instead of Real Integrations?
- Zero external dependencies or credentials required
- Immediate visual feedback for alerting workflows
- Safe for demonstration environments
- Easy to debug and customize

## Production Considerations

This playground demonstrates SRE concepts but would need these changes for production:

### Security
- Remove default passwords (Grafana admin/admin)
- Implement proper RBAC and network policies
- Add TLS termination and certificate management
- Secure container images and registries

### Scalability  
- Add horizontal pod autoscaling (HPA)
- Implement resource quotas and limits
- Add persistent storage for metrics retention
- Configure multi-zone deployments

### Reliability
- Set up cross-region clusters for disaster recovery
- Implement proper backup and restore procedures
- Add circuit breakers and rate limiting
- Configure proper health checks and liveness probes

## Troubleshooting

### Common Issues

**Cluster won't start**: 
```bash
docker system prune  # Clean up Docker
k3d cluster delete hrt-demo && k3d cluster create hrt-demo --agents 2
```

**Images not loading**:
```bash
make build-images
make load-images
```

**Port conflicts**:
```bash
# Check what's using ports
lsof -i :3000,8080,9090,9093
# Kill conflicting processes or change ports in Makefile
```

**Pods stuck in ImagePullBackOff**:
```bash
# Ensure images are loaded into k3d
k3d image list -c hrt-demo
make load-images
```

### Debug Commands
```bash
# Check cluster status
kubectl get nodes
kubectl get pods -A

# Check service connectivity
kubectl -n portal port-forward svc/portal 8080:80
curl http://localhost:8080/health

# View logs
kubectl -n portal logs -l app=portal
kubectl -n hrt-sre logs -l app=prometheus

# Check resource usage
kubectl top nodes
kubectl top pods -A
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes and add tests
4. Ensure CI pipeline passes
5. Submit pull request

### Development Setup
```bash
# Install development dependencies
pip install black flake8 pytest
npm install -g yamllint

# Run pre-commit checks
make lint
make test
```

## License

MIT License - see LICENSE file for details.

## Acknowledgments

- Inspired by Google's SRE practices and error budget management
- Built with cloud-native tools and Kubernetes best practices
- Prometheus monitoring patterns from the CNCF ecosystem

---

**Happy SRE-ing! 🚀**

For questions or issues, please check the [GitHub Issues](./issues) or contribute to the project.