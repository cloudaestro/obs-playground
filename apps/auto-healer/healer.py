import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional
from kubernetes import client
from kubernetes.client.rest import ApiException

logger = logging.getLogger(__name__)

class PodRestartHealer:
    """Helper class for analyzing and healing pods with high restart counts"""
    
    def __init__(self, v1_api: client.CoreV1Api, restart_threshold: int = 3):
        self.v1 = v1_api
        self.restart_threshold = restart_threshold
    
    def get_pod_restart_count(self, pod_name: str, namespace: str) -> int:
        """Get the maximum restart count for any container in a pod"""
        try:
            pod = self.v1.read_namespaced_pod(name=pod_name, namespace=namespace)
            
            if not pod.status.container_statuses:
                return 0
            
            max_restarts = 0
            for container in pod.status.container_statuses:
                if container.restart_count > max_restarts:
                    max_restarts = container.restart_count
            
            return max_restarts
            
        except ApiException as e:
            logger.error(f"Failed to get restart count for pod {pod_name}: {e}")
            return 0
    
    def is_pod_unhealthy(self, pod_name: str, namespace: str) -> bool:
        """Check if a pod is unhealthy based on restart count"""
        restart_count = self.get_pod_restart_count(pod_name, namespace)
        return restart_count >= self.restart_threshold
    
    def get_pod_health_status(self, pod_name: str, namespace: str) -> Dict:
        """Get comprehensive health status for a pod"""
        try:
            pod = self.v1.read_namespaced_pod(name=pod_name, namespace=namespace)
            
            status = {
                'name': pod_name,
                'namespace': namespace,
                'phase': pod.status.phase,
                'ready': False,
                'restart_count': 0,
                'containers': []
            }
            
            if pod.status.container_statuses:
                all_ready = True
                max_restarts = 0
                
                for container in pod.status.container_statuses:
                    container_info = {
                        'name': container.name,
                        'ready': container.ready,
                        'restart_count': container.restart_count,
                        'image': container.image,
                        'started': container.started
                    }
                    
                    if container.state:
                        if container.state.running:
                            container_info['state'] = 'running'
                            container_info['started_at'] = container.state.running.started_at
                        elif container.state.waiting:
                            container_info['state'] = 'waiting'
                            container_info['reason'] = container.state.waiting.reason
                        elif container.state.terminated:
                            container_info['state'] = 'terminated'
                            container_info['reason'] = container.state.terminated.reason
                    
                    status['containers'].append(container_info)
                    
                    if not container.ready:
                        all_ready = False
                    
                    if container.restart_count > max_restarts:
                        max_restarts = container.restart_count
                
                status['ready'] = all_ready
                status['restart_count'] = max_restarts
            
            return status
            
        except ApiException as e:
            logger.error(f"Failed to get health status for pod {pod_name}: {e}")
            return {
                'name': pod_name,
                'namespace': namespace,
                'error': str(e)
            }

class DeploymentPatcher:
    """Helper class for patching Kubernetes deployments"""
    
    def __init__(self, apps_v1_api: client.AppsV1Api):
        self.apps_v1 = apps_v1_api
    
    def restart_deployment(self, deployment_name: str, namespace: str) -> bool:
        """Restart a deployment by adding a restart annotation"""
        try:
            timestamp = datetime.now(timezone.utc).isoformat()
            
            patch = {
                "spec": {
                    "template": {
                        "metadata": {
                            "annotations": {
                                "kubectl.kubernetes.io/restartedAt": timestamp,
                                "auto-healer/restarted-at": timestamp,
                                "auto-healer/reason": "high-restart-count"
                            }
                        }
                    }
                }
            }
            
            self.apps_v1.patch_namespaced_deployment(
                name=deployment_name,
                namespace=namespace,
                body=patch
            )
            
            logger.info(f"Successfully patched deployment {deployment_name} in {namespace}")
            return True
            
        except ApiException as e:
            logger.error(f"Failed to patch deployment {deployment_name}: {e}")
            return False
    
    def get_deployment_status(self, deployment_name: str, namespace: str) -> Optional[Dict]:
        """Get deployment status information"""
        try:
            deployment = self.apps_v1.read_namespaced_deployment(
                name=deployment_name, 
                namespace=namespace
            )
            
            status = {
                'name': deployment_name,
                'namespace': namespace,
                'replicas': deployment.spec.replicas,
                'ready_replicas': deployment.status.ready_replicas or 0,
                'updated_replicas': deployment.status.updated_replicas or 0,
                'available_replicas': deployment.status.available_replicas or 0,
                'conditions': []
            }
            
            if deployment.status.conditions:
                for condition in deployment.status.conditions:
                    status['conditions'].append({
                        'type': condition.type,
                        'status': condition.status,
                        'reason': condition.reason,
                        'message': condition.message,
                        'last_transition_time': condition.last_transition_time
                    })
            
            return status
            
        except ApiException as e:
            logger.error(f"Failed to get deployment status for {deployment_name}: {e}")
            return None
    
    def scale_deployment(self, deployment_name: str, namespace: str, replicas: int) -> bool:
        """Scale a deployment to the specified number of replicas"""
        try:
            patch = {
                "spec": {
                    "replicas": replicas
                }
            }
            
            self.apps_v1.patch_namespaced_deployment(
                name=deployment_name,
                namespace=namespace,
                body=patch
            )
            
            logger.info(f"Successfully scaled deployment {deployment_name} to {replicas} replicas")
            return True
            
        except ApiException as e:
            logger.error(f"Failed to scale deployment {deployment_name}: {e}")
            return False

class NamespaceHealthChecker:
    """Helper class for checking overall namespace health"""
    
    def __init__(self, v1_api: client.CoreV1Api, apps_v1_api: client.AppsV1Api):
        self.v1 = v1_api
        self.apps_v1 = apps_v1_api
    
    def get_namespace_health_summary(self, namespace: str) -> Dict:
        """Get health summary for an entire namespace"""
        try:
            summary = {
                'namespace': namespace,
                'pods': {'total': 0, 'running': 0, 'pending': 0, 'failed': 0, 'unhealthy': 0},
                'deployments': {'total': 0, 'ready': 0},
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            pods = self.v1.list_namespaced_pod(namespace=namespace)
            for pod in pods.items:
                summary['pods']['total'] += 1
                
                if pod.status.phase == 'Running':
                    summary['pods']['running'] += 1
                elif pod.status.phase == 'Pending':
                    summary['pods']['pending'] += 1
                elif pod.status.phase == 'Failed':
                    summary['pods']['failed'] += 1
                
                if pod.status.container_statuses:
                    for container in pod.status.container_statuses:
                        if container.restart_count >= 3:
                            summary['pods']['unhealthy'] += 1
                            break
            
            deployments = self.apps_v1.list_namespaced_deployment(namespace=namespace)
            for deployment in deployments.items:
                summary['deployments']['total'] += 1
                
                if (deployment.status.ready_replicas and 
                    deployment.status.ready_replicas == deployment.spec.replicas):
                    summary['deployments']['ready'] += 1
            
            return summary
            
        except ApiException as e:
            logger.error(f"Failed to get namespace health summary for {namespace}: {e}")
            return {
                'namespace': namespace,
                'error': str(e),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }