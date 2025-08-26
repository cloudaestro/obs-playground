#!/usr/bin/env python3
"""
GitOps Watcher - A lightweight alternative to Argo CD for applying Kubernetes manifests

This script watches for changes in the k8s/ directory and applies them using kubectl.
Use this when you don't want to install Argo CD but still want GitOps-style deployment.
"""

import os
import sys
import time
import subprocess
import logging
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class K8sManifestHandler(FileSystemEventHandler):
    """Handle filesystem events for Kubernetes manifests"""
    
    def __init__(self, repo_path: str, overlay: str = "dev"):
        self.repo_path = Path(repo_path)
        self.overlay = overlay
        self.overlay_path = self.repo_path / "k8s" / "overlays" / overlay
        self.last_applied = {}
        self.debounce_seconds = 5
        
    def on_modified(self, event):
        if event.is_directory:
            return
            
        file_path = Path(event.src_path)
        
        if not self._is_k8s_file(file_path):
            return
            
        logger.info(f"Detected change in {file_path}")
        self._debounce_and_apply(file_path)
    
    def on_created(self, event):
        self.on_modified(event)
    
    def _is_k8s_file(self, file_path: Path) -> bool:
        """Check if file is a Kubernetes manifest"""
        k8s_extensions = {'.yaml', '.yml', '.json'}
        k8s_dirs = {'k8s', 'manifests', 'monitoring'}
        
        if file_path.suffix not in k8s_extensions:
            return False
            
        # Check if file is in a k8s-related directory
        for part in file_path.parts:
            if any(k8s_dir in part.lower() for k8s_dir in k8s_dirs):
                return True
                
        return False
    
    def _debounce_and_apply(self, file_path: Path):
        """Debounce rapid changes and apply manifests"""
        now = time.time()
        file_key = str(file_path)
        
        if file_key in self.last_applied:
            if now - self.last_applied[file_key] < self.debounce_seconds:
                logger.debug(f"Debouncing {file_path}, waiting...")
                return
        
        self.last_applied[file_key] = now
        time.sleep(2)  # Small delay to ensure file write is complete
        
        self._apply_manifests()
    
    def _apply_manifests(self):
        """Apply Kubernetes manifests using kubectl"""
        try:
            if not self.overlay_path.exists():
                logger.error(f"Overlay path does not exist: {self.overlay_path}")
                return
            
            logger.info(f"Applying manifests from {self.overlay_path}")
            
            # Use kustomize if available, otherwise apply directly
            if (self.overlay_path / "kustomization.yaml").exists():
                cmd = ["kubectl", "apply", "-k", str(self.overlay_path)]
            else:
                cmd = ["kubectl", "apply", "-f", str(self.overlay_path)]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.repo_path
            )
            
            if result.returncode == 0:
                logger.info("Successfully applied manifests")
                logger.debug(f"kubectl output: {result.stdout}")
            else:
                logger.error(f"Failed to apply manifests: {result.stderr}")
                
        except subprocess.CalledProcessError as e:
            logger.error(f"kubectl command failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error applying manifests: {e}")

def check_prerequisites():
    """Check if required tools are available"""
    required_tools = ['kubectl']
    
    for tool in required_tools:
        try:
            subprocess.run([tool, 'version', '--client'], 
                         capture_output=True, check=True)
            logger.info(f"{tool} is available")
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.error(f"{tool} is not available or not working")
            return False
    
    return True

def initial_apply(handler: K8sManifestHandler):
    """Perform initial application of manifests"""
    logger.info("Performing initial manifest application...")
    handler._apply_manifests()

def main():
    if len(sys.argv) > 1:
        repo_path = sys.argv[1]
    else:
        repo_path = os.getcwd()
    
    overlay = os.getenv('GITOPS_OVERLAY', 'dev')
    watch_interval = int(os.getenv('GITOPS_WATCH_INTERVAL', '10'))
    
    logger.info(f"Starting GitOps watcher for {repo_path} (overlay: {overlay})")
    
    if not check_prerequisites():
        logger.error("Prerequisites not met, exiting")
        sys.exit(1)
    
    # Set up file system watcher
    event_handler = K8sManifestHandler(repo_path, overlay)
    observer = Observer()
    observer.schedule(
        event_handler, 
        path=str(Path(repo_path) / "k8s"),
        recursive=True
    )
    observer.schedule(
        event_handler,
        path=str(Path(repo_path) / "monitoring"),
        recursive=True
    )
    
    # Initial application
    initial_apply(event_handler)
    
    # Start watching
    observer.start()
    logger.info("GitOps watcher started. Press Ctrl+C to stop.")
    
    try:
        while True:
            time.sleep(watch_interval)
    except KeyboardInterrupt:
        logger.info("Stopping GitOps watcher...")
        observer.stop()
    
    observer.join()
    logger.info("GitOps watcher stopped")

if __name__ == "__main__":
    main()