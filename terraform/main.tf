terraform {
  required_version = ">= 1.0"
  required_providers {
    null = {
      source  = "hashicorp/null"
      version = "~> 3.1"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.2"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.4"
    }
  }
}

# Infrastructure-as-Code demonstration using null and local providers
# This module simulates infrastructure provisioning without cloud credentials

resource "local_file" "cluster_config" {
  filename = "${path.module}/../generated/cluster-config.yaml"
  content = templatefile("${path.module}/templates/cluster-config.yaml.tpl", {
    cluster_name     = var.cluster_name
    node_count       = var.node_count
    namespace        = var.namespace
    portal_namespace = var.portal_namespace
    timestamp        = timestamp()
  })

  provisioner "local-exec" {
    command = "mkdir -p ${path.module}/../generated"
  }
}

resource "local_file" "monitoring_config" {
  filename = "${path.module}/../generated/monitoring-config.yaml"
  content = templatefile("${path.module}/templates/monitoring-config.yaml.tpl", {
    retention_days      = var.monitoring_retention_days
    scrape_interval     = var.scrape_interval
    evaluation_interval = var.evaluation_interval
    alert_webhook_url   = var.alert_webhook_url
  })
}

resource "null_resource" "validate_config" {
  depends_on = [
    local_file.cluster_config,
    local_file.monitoring_config
  ]

  triggers = {
    cluster_config_hash    = local_file.cluster_config.content_md5
    monitoring_config_hash = local_file.monitoring_config.content_md5
  }

  provisioner "local-exec" {
    command = <<-EOT
      echo "Validating configuration files..."
      echo "Cluster config: ${local_file.cluster_config.filename}"
      echo "Monitoring config: ${local_file.monitoring_config.filename}"
      echo "Configuration validation completed at: $(date)"
    EOT
  }
}

resource "local_file" "deployment_summary" {
  filename = "${path.module}/../generated/deployment-summary.json"
  content = jsonencode({
    deployment_id = random_id.deployment_id.hex
    cluster_name  = var.cluster_name
    namespaces    = [var.namespace, var.portal_namespace]
    components = {
      portal      = true
      batch_sync  = true
      auto_healer = true
      monitoring  = true
      gitops      = var.enable_gitops
    }
    generated_at = timestamp()
  })
}

resource "random_id" "deployment_id" {
  byte_length = 8
}