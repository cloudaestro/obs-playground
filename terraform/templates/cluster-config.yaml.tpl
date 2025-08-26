apiVersion: v1
kind: ConfigMap
metadata:
  name: cluster-config
  namespace: ${namespace}
data:
  cluster.yaml: |
    name: ${cluster_name}
    nodeCount: ${node_count}
    namespaces:
      - ${namespace}
      - ${portal_namespace}
    generatedAt: "${timestamp}"
    features:
      monitoring: true
      autoHealing: true
      gitops: true
    ports:
      - name: grafana
        port: 3000
        protocol: TCP
      - name: prometheus
        port: 9090
        protocol: TCP
      - name: portal
        port: 8080
        protocol: TCP