apiVersion: v1
kind: ConfigMap
metadata:
  name: monitoring-config
  namespace: hrt-sre
data:
  prometheus.yaml: |
    global:
      scrape_interval: ${scrape_interval}
      evaluation_interval: ${evaluation_interval}
    
    rule_files:
      - /etc/prometheus/rules/*.yml
    
    alerting:
      alertmanagers:
        - static_configs:
            - targets:
              - alertmanager:9093
    
    scrape_configs:
      - job_name: 'prometheus'
        static_configs:
          - targets: ['localhost:9090']
      
      - job_name: 'portal'
        static_configs:
          - targets: ['portal.portal:80']
        metrics_path: /metrics
        scrape_interval: ${scrape_interval}
  
  alertmanager.yaml: |
    global:
      smtp_smarthost: 'localhost:587'
      smtp_from: 'alertmanager@hrt-sre.local'
    
    route:
      group_by: ['alertname']
      group_wait: 10s
      group_interval: 10s
      repeat_interval: 1h
      receiver: 'mock-slack'
    
    receivers:
      - name: 'mock-slack'
        webhook_configs:
          - url: '${alert_webhook_url}'
            send_resolved: true
  
  retention: "${retention_days}d"