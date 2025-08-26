import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
from kubernetes.client.rest import ApiException

from healer import PodRestartHealer, DeploymentPatcher, NamespaceHealthChecker

class TestPodRestartHealer(unittest.TestCase):
    def setUp(self):
        self.mock_v1_api = Mock()
        self.healer = PodRestartHealer(self.mock_v1_api, restart_threshold=3)
    
    def test_get_pod_restart_count_success(self):
        mock_pod = Mock()
        mock_container = Mock()
        mock_container.restart_count = 5
        mock_pod.status.container_statuses = [mock_container]
        
        self.mock_v1_api.read_namespaced_pod.return_value = mock_pod
        
        result = self.healer.get_pod_restart_count("test-pod", "test-namespace")
        
        self.assertEqual(result, 5)
        self.mock_v1_api.read_namespaced_pod.assert_called_once_with(
            name="test-pod", namespace="test-namespace"
        )
    
    def test_get_pod_restart_count_multiple_containers(self):
        mock_pod = Mock()
        mock_container1 = Mock()
        mock_container1.restart_count = 2
        mock_container2 = Mock()
        mock_container2.restart_count = 7
        mock_pod.status.container_statuses = [mock_container1, mock_container2]
        
        self.mock_v1_api.read_namespaced_pod.return_value = mock_pod
        
        result = self.healer.get_pod_restart_count("test-pod", "test-namespace")
        
        self.assertEqual(result, 7)
    
    def test_get_pod_restart_count_no_containers(self):
        mock_pod = Mock()
        mock_pod.status.container_statuses = None
        
        self.mock_v1_api.read_namespaced_pod.return_value = mock_pod
        
        result = self.healer.get_pod_restart_count("test-pod", "test-namespace")
        
        self.assertEqual(result, 0)
    
    def test_get_pod_restart_count_api_exception(self):
        self.mock_v1_api.read_namespaced_pod.side_effect = ApiException("API Error")
        
        result = self.healer.get_pod_restart_count("test-pod", "test-namespace")
        
        self.assertEqual(result, 0)
    
    def test_is_pod_unhealthy_true(self):
        with patch.object(self.healer, 'get_pod_restart_count', return_value=5):
            result = self.healer.is_pod_unhealthy("test-pod", "test-namespace")
            self.assertTrue(result)
    
    def test_is_pod_unhealthy_false(self):
        with patch.object(self.healer, 'get_pod_restart_count', return_value=2):
            result = self.healer.is_pod_unhealthy("test-pod", "test-namespace")
            self.assertFalse(result)
    
    def test_get_pod_health_status_success(self):
        mock_pod = Mock()
        mock_pod.status.phase = "Running"
        
        mock_container = Mock()
        mock_container.name = "test-container"
        mock_container.ready = True
        mock_container.restart_count = 2
        mock_container.image = "test:latest"
        mock_container.started = True
        
        mock_running_state = Mock()
        mock_running_state.started_at = datetime.now(timezone.utc)
        mock_container.state.running = mock_running_state
        mock_container.state.waiting = None
        mock_container.state.terminated = None
        
        mock_pod.status.container_statuses = [mock_container]
        
        self.mock_v1_api.read_namespaced_pod.return_value = mock_pod
        
        result = self.healer.get_pod_health_status("test-pod", "test-namespace")
        
        expected = {
            'name': 'test-pod',
            'namespace': 'test-namespace',
            'phase': 'Running',
            'ready': True,
            'restart_count': 2,
            'containers': [{
                'name': 'test-container',
                'ready': True,
                'restart_count': 2,
                'image': 'test:latest',
                'started': True,
                'state': 'running',
                'started_at': mock_running_state.started_at
            }]
        }
        
        self.assertEqual(result['name'], expected['name'])
        self.assertEqual(result['phase'], expected['phase'])
        self.assertEqual(result['ready'], expected['ready'])
        self.assertEqual(result['restart_count'], expected['restart_count'])

class TestDeploymentPatcher(unittest.TestCase):
    def setUp(self):
        self.mock_apps_v1_api = Mock()
        self.patcher = DeploymentPatcher(self.mock_apps_v1_api)
    
    @patch('healer.datetime')
    def test_restart_deployment_success(self, mock_datetime):
        mock_datetime.utcnow.return_value.isoformat.return_value = "2024-01-01T12:00:00"
        
        result = self.patcher.restart_deployment("test-deployment", "test-namespace")
        
        self.assertTrue(result)
        self.mock_apps_v1_api.patch_namespaced_deployment.assert_called_once()
        
        call_args = self.mock_apps_v1_api.patch_namespaced_deployment.call_args
        self.assertEqual(call_args[1]['name'], 'test-deployment')
        self.assertEqual(call_args[1]['namespace'], 'test-namespace')
        
        patch_body = call_args[1]['body']
        self.assertIn('kubectl.kubernetes.io/restartedAt', 
                      patch_body['spec']['template']['metadata']['annotations'])
    
    def test_restart_deployment_api_exception(self):
        self.mock_apps_v1_api.patch_namespaced_deployment.side_effect = ApiException("API Error")
        
        result = self.patcher.restart_deployment("test-deployment", "test-namespace")
        
        self.assertFalse(result)
    
    def test_get_deployment_status_success(self):
        mock_deployment = Mock()
        mock_deployment.spec.replicas = 3
        mock_deployment.status.ready_replicas = 2
        mock_deployment.status.updated_replicas = 3
        mock_deployment.status.available_replicas = 2
        mock_deployment.status.conditions = []
        
        self.mock_apps_v1_api.read_namespaced_deployment.return_value = mock_deployment
        
        result = self.patcher.get_deployment_status("test-deployment", "test-namespace")
        
        expected = {
            'name': 'test-deployment',
            'namespace': 'test-namespace',
            'replicas': 3,
            'ready_replicas': 2,
            'updated_replicas': 3,
            'available_replicas': 2,
            'conditions': []
        }
        
        self.assertEqual(result, expected)
    
    def test_scale_deployment_success(self):
        result = self.patcher.scale_deployment("test-deployment", "test-namespace", 5)
        
        self.assertTrue(result)
        self.mock_apps_v1_api.patch_namespaced_deployment.assert_called_once()
        
        call_args = self.mock_apps_v1_api.patch_namespaced_deployment.call_args
        patch_body = call_args[1]['body']
        self.assertEqual(patch_body['spec']['replicas'], 5)

class TestNamespaceHealthChecker(unittest.TestCase):
    def setUp(self):
        self.mock_v1_api = Mock()
        self.mock_apps_v1_api = Mock()
        self.checker = NamespaceHealthChecker(self.mock_v1_api, self.mock_apps_v1_api)
    
    def test_get_namespace_health_summary_success(self):
        mock_pod1 = Mock()
        mock_pod1.status.phase = "Running"
        mock_pod1.status.container_statuses = [Mock(restart_count=1)]
        
        mock_pod2 = Mock()
        mock_pod2.status.phase = "Running"
        mock_pod2.status.container_statuses = [Mock(restart_count=5)]
        
        mock_pods_list = Mock()
        mock_pods_list.items = [mock_pod1, mock_pod2]
        self.mock_v1_api.list_namespaced_pod.return_value = mock_pods_list
        
        mock_deployment = Mock()
        mock_deployment.spec.replicas = 2
        mock_deployment.status.ready_replicas = 2
        
        mock_deployments_list = Mock()
        mock_deployments_list.items = [mock_deployment]
        self.mock_apps_v1_api.list_namespaced_deployment.return_value = mock_deployments_list
        
        result = self.checker.get_namespace_health_summary("test-namespace")
        
        self.assertEqual(result['namespace'], 'test-namespace')
        self.assertEqual(result['pods']['total'], 2)
        self.assertEqual(result['pods']['running'], 2)
        self.assertEqual(result['pods']['unhealthy'], 1)
        self.assertEqual(result['deployments']['total'], 1)
        self.assertEqual(result['deployments']['ready'], 1)

if __name__ == '__main__':
    unittest.main()