variable "cluster_name" {
  description = "Name of the k3d cluster"
  type        = string
  default     = "hrt-demo"
}

variable "node_count" {
  description = "Number of worker nodes in the cluster"
  type        = number
  default     = 2
}

variable "namespace" {
  description = "Main namespace for SRE components"
  type        = string
  default     = "hrt-sre"
}

variable "portal_namespace" {
  description = "Namespace for the portal application"
  type        = string
  default     = "portal"
}

variable "monitoring_retention_days" {
  description = "Prometheus data retention in days"
  type        = number
  default     = 7
}

variable "scrape_interval" {
  description = "Prometheus scrape interval"
  type        = string
  default     = "15s"
}

variable "evaluation_interval" {
  description = "Prometheus rule evaluation interval"
  type        = string
  default     = "15s"
}

variable "alert_webhook_url" {
  description = "Webhook URL for alert notifications"
  type        = string
  default     = "http://mock-slack:8080/webhook"
}

variable "enable_gitops" {
  description = "Enable GitOps components (Argo CD)"
  type        = bool
  default     = false
}