import logging
import os
import threading
import time
from app.database import connection, POOL_MAX_SIZE


logger = logging.getLogger("argus.worker")


class IngestionWorkers:
    def __init__(self):
        self.count = int(os.getenv("ARGUS_INGESTION_WORKERS", "1"))
        self.poll_seconds = float(os.getenv("ARGUS_INGESTION_POLL_SECONDS", "1"))
        self.shutdown_seconds = float(os.getenv("ARGUS_INGESTION_SHUTDOWN_SECONDS", "5"))
        if not 0 <= self.count <= 32:
            raise ValueError("ARGUS_INGESTION_WORKERS must be between 0 and 32")
        if self.count * 4 + 8 > POOL_MAX_SIZE:
            raise ValueError("Database pool must reserve four connections per ingestion worker plus eight for API operations")
        if not 0.1 <= self.poll_seconds <= 60:
            raise ValueError("ARGUS_INGESTION_POLL_SECONDS must be between 0.1 and 60")
        if not 0 <= self.shutdown_seconds <= 60:
            raise ValueError("ARGUS_INGESTION_SHUTDOWN_SECONDS must be between 0 and 60")
        self.stop_event = threading.Event()
        self.threads = []
        self.active = {}
        self.state_lock = threading.Lock()

    def start(self):
        for number in range(self.count):
            thread = threading.Thread(target=self.loop, args=(number,), name=f"argus-ingestion-{number}", daemon=True)
            self.threads.append(thread)
            thread.start()
        logger.info("Started %s bounded ingestion workers", self.count)

    def loop(self, number):
        slot=f"argus-ingestion-worker-slot:{number}"
        while not self.stop_event.is_set():
            try:
                with connection() as lease:
                    acquired=lease.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS acquired",(slot,)).fetchone()["acquired"]
                    lease.commit()
                    if not acquired:
                        self.stop_event.wait(self.poll_seconds)
                        continue
                    try:
                        self.process_queue(number)
                    finally:
                        lease.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))",(slot,))
            except Exception:
                logger.exception("Ingestion worker slot could not be acquired")
                self.stop_event.wait(self.poll_seconds)

    def process_queue(self, number):
        from app.ingestion.pipeline import IngestionPipeline
        pipeline = IngestionPipeline()
        while not self.stop_event.is_set():
            try:
                with connection() as conn:
                    candidates = conn.execute("SELECT id,queued_through FROM ingestion_jobs WHERE status='queued' AND queued_through IS NOT NULL ORDER BY created_at,id LIMIT %s", (max(8,self.count*2),)).fetchall()
                if not candidates:
                    self.stop_event.wait(self.poll_seconds)
                    continue
                for candidate in candidates:
                    if self.stop_event.is_set():
                        break
                    with self.state_lock:
                        self.active[number] = candidate["id"]
                    try:
                        pipeline.run_job(candidate["id"], candidate["queued_through"], queued_only=True)
                    except Exception as error:
                        logger.exception("Queued ingestion job failed outside its stage handler: %s",candidate["id"])
                        with connection() as conn:
                            conn.execute("UPDATE ingestion_jobs SET status='failed',error=%s,updated_at=now() WHERE id=%s AND status='running'", (str(error),candidate["id"]))
                    finally:
                        with self.state_lock:
                            self.active.pop(number,None)
                self.stop_event.wait(self.poll_seconds)
            except Exception:
                logger.exception("Ingestion queue could not be polled")
                self.stop_event.wait(self.poll_seconds)

    def stop(self):
        self.stop_event.set()
        deadline = time.monotonic()+self.shutdown_seconds
        for thread in self.threads:
            thread.join(max(0,deadline-time.monotonic()))
        with self.state_lock:
            remaining = list(self.active.values())
        if remaining:
            logger.warning("Shutdown wait ended with %s active ingestion jobs; persisted stage artifacts remain resumable",len(remaining))

    def status(self):
        with self.state_lock:
            active = list(self.active.values())
        return {"configuredWorkers":self.count,"activeJobs":active,"stopping":self.stop_event.is_set(),"queue":"postgres","automaticRetry":False,"concurrencyScope":"database advisory worker slots"}
