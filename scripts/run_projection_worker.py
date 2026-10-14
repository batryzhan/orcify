"""Run the local Neo4j outbox consumer until interrupted."""

from __future__ import annotations

import logging
import os
import time

from neo4j import GraphDatabase
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.api.app.neo4j_projection import Neo4jGraphProjection
from services.api.app.projection_worker import WorkerConfig, process_next, reconcile_all

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("orcify.projection")


def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    neo4j_uri = os.environ.get("NEO4J_URI")
    neo4j_user = os.environ.get("NEO4J_USER")
    neo4j_password = os.environ.get("NEO4J_PASSWORD")
    if not all((database_url, neo4j_uri, neo4j_user, neo4j_password)):
        raise SystemExit("DATABASE_URL and NEO4J_URI/USER/PASSWORD are required")
    assert database_url is not None
    assert neo4j_uri is not None
    assert neo4j_user is not None
    assert neo4j_password is not None

    engine = create_engine(database_url, pool_pre_ping=True)
    sessions = sessionmaker(engine, expire_on_commit=False)
    driver = GraphDatabase.driver(
        neo4j_uri,
        auth=(neo4j_user, neo4j_password),
        connection_timeout=5,
        max_transaction_retry_time=10,
    )
    projection = Neo4jGraphProjection(driver)
    try:
        driver.verify_connectivity()
        projection.ensure_schema()
        config = WorkerConfig()
        last_reconcile = 0.0
        while True:
            clock = time.monotonic()
            if clock - last_reconcile >= 60:
                for reconciliation in reconcile_all(sessions, projection):
                    if reconciliation.error is not None:
                        logger.error(
                            "projection reconciliation failed for tenant=%s project=%s: %s",
                            reconciliation.tenant_id,
                            reconciliation.project_id,
                            reconciliation.error,
                        )
                last_reconcile = clock
            result = process_next(sessions, projection, config)
            if not result.claimed:
                time.sleep(0.5)
            elif not result.succeeded:
                logger.warning(
                    "projection delivery id=%s status=%s revision=%s: %s",
                    result.outbox_id,
                    result.status,
                    result.source_revision,
                    result.error,
                )
    except KeyboardInterrupt:
        logger.info("projection worker stopped")
    finally:
        driver.close()
        engine.dispose()


if __name__ == "__main__":
    main()
