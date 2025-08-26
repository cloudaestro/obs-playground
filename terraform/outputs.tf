output "cluster_name" {
  description = "Name of the k3d cluster"
  value       = var.cluster_name
}

output "namespaces" {
  description = "Kubernetes namespaces created"
  value       = [var.namespace, var.portal_namespace]
}

output "deployment_id" {
  description = "Unique deployment identifier"
  value       = random_id.deployment_id.hex
}

output "config_files" {
  description = "Generated configuration files"
  value = {
    cluster_config    = local_file.cluster_config.filename
    monitoring_config = local_file.monitoring_config.filename
    deployment_summary = local_file.deployment_summary.filename
  }
}

output "monitoring_endpoints" {
  description = "Monitoring service endpoints"
  value = {
    prometheus = "http://localhost:9090"
    grafana    = "http://localhost:3000"
    alertmanager = "http://localhost:9093"
  }
}

output "application_endpoints" {
  description = "Application service endpoints"
  value = {
    portal = "http://localhost:8080"
    mock_slack = "http://localhost:8080/webhook"
  }
}