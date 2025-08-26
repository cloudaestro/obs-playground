import os
import time
import json
import random
import logging
from datetime import datetime, timedelta, timezone
from prometheus_client import Counter, Histogram, Gauge, push_to_gateway
import requests

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

SYNC_COUNTER = Counter('batch_sync_operations_total', 'Total sync operations', ['status'])
SYNC_DURATION = Histogram('batch_sync_duration_seconds', 'Time spent on sync operations')
RECORDS_PROCESSED = Gauge('batch_sync_records_processed', 'Number of records processed in last run')
SYNC_ERRORS = Counter('batch_sync_errors_total', 'Total sync errors', ['error_type'])

class BatchSyncService:
    def __init__(self):
        self.prometheus_gateway = os.getenv('PROMETHEUS_GATEWAY', 'prometheus-pushgateway:9091')
        self.batch_size = int(os.getenv('BATCH_SIZE', '1000'))
        self.failure_rate = float(os.getenv('FAILURE_RATE', '0.1'))
        self.job_name = 'batch-sync'
        
    def fetch_data_batch(self, offset: int, limit: int) -> list:
        """Simulate fetching data from external source"""
        logger.info(f"Fetching batch: offset={offset}, limit={limit}")
        
        if random.random() < self.failure_rate:
            error_msg = "External API timeout"
            SYNC_ERRORS.labels(error_type='api_timeout').inc()
            raise Exception(error_msg)
        
        time.sleep(random.uniform(0.5, 2.0))
        
        records = []
        for i in range(limit):
            records.append({
                'id': offset + i + 1,
                'name': f'record_{offset + i + 1}',
                'value': random.randint(1, 1000),
                'updated_at': datetime.now(timezone.utc).isoformat(),
                'source': 'external_api'
            })
        
        return records
    
    def process_record(self, record: dict) -> bool:
        """Process individual record"""
        try:
            if random.random() < 0.05:
                raise ValueError(f"Invalid data in record {record['id']}")
            
            time.sleep(random.uniform(0.01, 0.05))
            record['processed_at'] = datetime.now(timezone.utc).isoformat()
            record['status'] = 'processed'
            
            return True
        except Exception as e:
            logger.warning(f"Failed to process record {record['id']}: {e}")
            SYNC_ERRORS.labels(error_type='processing').inc()
            return False
    
    def store_batch(self, records: list) -> int:
        """Simulate storing processed records"""
        logger.info(f"Storing {len(records)} records")
        
        if random.random() < self.failure_rate * 0.5:
            SYNC_ERRORS.labels(error_type='storage').inc()
            raise Exception("Database connection failed")
        
        time.sleep(random.uniform(0.1, 0.5))
        stored_count = len([r for r in records if r.get('status') == 'processed'])
        
        logger.info(f"Successfully stored {stored_count} records")
        return stored_count
    
    @SYNC_DURATION.time()
    def run_sync(self):
        """Main sync operation"""
        logger.info("Starting batch sync operation")
        
        try:
            total_processed = 0
            total_batches = random.randint(3, 8)
            
            for batch_num in range(total_batches):
                logger.info(f"Processing batch {batch_num + 1}/{total_batches}")
                
                try:
                    offset = batch_num * self.batch_size
                    records = self.fetch_data_batch(offset, self.batch_size)
                    
                    processed_records = []
                    for record in records:
                        if self.process_record(record):
                            processed_records.append(record)
                    
                    if processed_records:
                        stored_count = self.store_batch(processed_records)
                        total_processed += stored_count
                
                except Exception as e:
                    logger.error(f"Batch {batch_num + 1} failed: {e}")
                    continue
            
            RECORDS_PROCESSED.set(total_processed)
            SYNC_COUNTER.labels(status='success').inc()
            
            logger.info(f"Sync completed successfully. Processed {total_processed} records")
            return True
            
        except Exception as e:
            logger.error(f"Sync operation failed: {e}")
            SYNC_COUNTER.labels(status='failure').inc()
            return False
    
    def push_metrics(self):
        """Push metrics to Prometheus pushgateway"""
        try:
            registry = CollectorRegistry()
            registry.register(SYNC_COUNTER)
            registry.register(SYNC_DURATION)
            registry.register(RECORDS_PROCESSED)
            registry.register(SYNC_ERRORS)
            
            push_to_gateway(
                self.prometheus_gateway,
                job=self.job_name,
                registry=registry
            )
            logger.info("Metrics pushed successfully")
        except Exception as e:
            logger.warning(f"Failed to push metrics: {e}")

def main():
    logger.info("Batch sync job starting")
    
    sync_service = BatchSyncService()
    
    start_time = datetime.now(timezone.utc)
    success = sync_service.run_sync()
    end_time = datetime.now(timezone.utc)
    
    duration = (end_time - start_time).total_seconds()
    
    status = "SUCCESS" if success else "FAILURE"
    logger.info(f"Batch sync completed with status: {status} (duration: {duration:.2f}s)")
    
    sync_service.push_metrics()
    
    summary = {
        'job': 'batch-sync',
        'status': status,
        'start_time': start_time.isoformat(),
        'end_time': end_time.isoformat(),
        'duration_seconds': duration,
        'records_processed': RECORDS_PROCESSED._value.get()
    }
    
    logger.info(f"Job summary: {json.dumps(summary, indent=2)}")
    
    if not success:
        exit(1)

if __name__ == "__main__":
    from prometheus_client import CollectorRegistry
    main()