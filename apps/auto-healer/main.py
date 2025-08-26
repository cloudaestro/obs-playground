import os
import time
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from kubernetes import client, config
from kubernetes.client.rest import ApiException
from prometheus_client import Counter, Gauge, push_to_gateway, CollectorRegistry

from healer import PodRestartHealer, DeploymentPatcher

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

HEAL_ACTIONS = Counter('auto_healer_actions_total', 'Total healing actions', ['type', 'namespace', 'resource'])
UNHEALTHY_PODS = Gauge('auto_healer_unhealthy_pods', 'Number of unhealthy pods detected')
HEAL_ERRORS = Counter('auto_healer_errors_total', 'Total healing errors', ['error_type'])

class AutoHealerService:
    def __init__(self):
        self.restart_threshold = int(os.getenv('RESTART_THRESHOLD', '3'))
        self.check_interval = int(os.getenv('CHECK_INTERVAL', '60'))
        self.prometheus_gateway = os.getenv('PROMETHEUS_GATEWAY', 'prometheus-pushgateway:9091')
        self.job_name = 'auto-healer'
        self.dry_run = os.getenv('DRY_RUN', 'false').lower() == 'true'
        
        try:
            config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes configuration")
        except:
            try:
                config.load_kube_config()
                logger.info("Loaded local Kubernetes configuration")
            except Exception as e:
                logger.error(f"Failed to load Kubernetes configuration: {e}")
                raise
        
        self.v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        
        self.healer = PodRestartHealer(self.v1, self.restart_threshold)
        self.patcher = DeploymentPatcher(self.apps_v1)
    
    def get_unhealthy_pods(self, namespaces: Optional[List[str]] = None) -> Dict[str, List]:
        """Get pods with high restart counts across specified namespaces"""
        unhealthy_pods = {}
        
        if namespaces is None:
            namespaces = ['portal', 'hrt-sre']
        
        for namespace in namespaces:
            try:
                pods = self.v1.list_namespaced_pod(namespace=namespace)
                unhealthy = []
                
                for pod in pods.items:
                    if pod.status.container_statuses:
                        for container in pod.status.container_statuses:
                            if container.restart_count >= self.restart_threshold:
                                unhealthy.append({
                                    'name': pod.metadata.name,
                                    'namespace': namespace,
                                    'restart_count': container.restart_count,
                                    'container': container.name,
                                    'image': container.image,
                                    'ready': container.ready,
                                    'last_restart': container.last_termination_time
                                })
                
                if unhealthy:
                    unhealthy_pods[namespace] = unhealthy
                    logger.info(f"Found {len(unhealthy)} unhealthy pods in namespace {namespace}")
                
            except ApiException as e:
                logger.error(f"Failed to list pods in namespace {namespace}: {e}")
                HEAL_ERRORS.labels(error_type='api_error').inc()
        
        return unhealthy_pods
    
    def heal_deployment(self, pod_info: dict) -> bool:
        """Attempt to heal a deployment by triggering a rollout restart"""
        namespace = pod_info['namespace']
        pod_name = pod_info['name']
        
        try:
            pod = self.v1.read_namespaced_pod(name=pod_name, namespace=namespace)
            
            if not pod.metadata.owner_references:
                logger.warning(f"Pod {pod_name} has no owner references, skipping")
                return False
            
            for owner in pod.metadata.owner_references:
                if owner.kind == 'ReplicaSet':
                    rs = self.apps_v1.read_namespaced_replica_set(
                        name=owner.name, 
                        namespace=namespace
                    )
                    
                    if rs.metadata.owner_references:
                        for rs_owner in rs.metadata.owner_references:
                            if rs_owner.kind == 'Deployment':
                                deployment_name = rs_owner.name
                                
                                logger.info(f"Healing deployment {deployment_name} in {namespace}")
                                
                                if self.dry_run:
                                    logger.info(f"DRY RUN: Would restart deployment {deployment_name}")
                                    HEAL_ACTIONS.labels(
                                        type='dry_run_restart',
                                        namespace=namespace,
                                        resource=deployment_name
                                    ).inc()
                                    return True
                                
                                success = self.patcher.restart_deployment(deployment_name, namespace)
                                
                                if success:
                                    HEAL_ACTIONS.labels(
                                        type='restart',
                                        namespace=namespace,
                                        resource=deployment_name
                                    ).inc()
                                    logger.info(f"Successfully triggered restart for {deployment_name}")
                                    return True
                                else:
                                    HEAL_ERRORS.labels(error_type='patch_failed').inc()
                                    return False
            
            logger.warning(f"Could not find deployment for pod {pod_name}")
            return False
            
        except ApiException as e:
            logger.error(f"Failed to heal pod {pod_name}: {e}")
            HEAL_ERRORS.labels(error_type='api_error').inc()
            return False
    
    def run_healing_cycle(self):
        """Run one healing cycle"""
        logger.info("Starting auto-healer cycle")
        
        try:
            unhealthy_pods = self.get_unhealthy_pods()
            
            total_unhealthy = sum(len(pods) for pods in unhealthy_pods.values())
            UNHEALTHY_PODS.set(total_unhealthy)
            
            if not unhealthy_pods:
                logger.info("No unhealthy pods found")
                return
            
            logger.info(f"Found {total_unhealthy} unhealthy pods across {len(unhealthy_pods)} namespaces")
            
            healed_count = 0
            for namespace, pods in unhealthy_pods.items():
                for pod_info in pods:
                    logger.info(
                        f"Pod {pod_info['name']} in {namespace} has "
                        f"{pod_info['restart_count']} restarts (threshold: {self.restart_threshold})"
                    )
                    
                    if self.heal_deployment(pod_info):
                        healed_count += 1
                        time.sleep(2)
            
            logger.info(f"Healing cycle completed. Healed {healed_count} deployments")
            
        except Exception as e:
            logger.error(f"Healing cycle failed: {e}")
            HEAL_ERRORS.labels(error_type='cycle_error').inc()
    
    def push_metrics(self):
        """Push metrics to Prometheus pushgateway"""
        try:
            registry = CollectorRegistry()
            registry.register(HEAL_ACTIONS)
            registry.register(UNHEALTHY_PODS)
            registry.register(HEAL_ERRORS)
            
            push_to_gateway(
                self.prometheus_gateway,
                job=self.job_name,
                registry=registry
            )
            logger.info("Metrics pushed successfully")
        except Exception as e:
            logger.warning(f"Failed to push metrics: {e}")

def main():
    logger.info("Auto-healer starting")
    
    healer_service = AutoHealerService()
    
    start_time = datetime.now(timezone.utc)
    
    try:
        healer_service.run_healing_cycle()
        status = "SUCCESS"
    except Exception as e:
        logger.error(f"Auto-healer failed: {e}")
        status = "FAILURE"
    
    end_time = datetime.now(timezone.utc)
    duration = (end_time - start_time).total_seconds()
    
    logger.info(f"Auto-healer completed with status: {status} (duration: {duration:.2f}s)")
    
    healer_service.push_metrics()
    
    summary = {
        'job': 'auto-healer',
        'status': status,
        'start_time': start_time.isoformat(),
        'end_time': end_time.isoformat(),
        'duration_seconds': duration,
        'restart_threshold': healer_service.restart_threshold,
        'dry_run': healer_service.dry_run
    }
    
    logger.info(f"Job summary: {json.dumps(summary, indent=2)}")

if __name__ == "__main__":
    main()