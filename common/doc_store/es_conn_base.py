import os
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
from common.log_utils import getLogger

logger = getLogger("ElasticsearchConn")

class ElasticsearchConnection:
    def __init__(self):
        # Configure ES connection using MVP credentials
        # Default config per docker-compose-base.yml
        self.host = os.environ.get("ES_HOST", "localhost")
        self.port = int(os.environ.get("ES_PORT", 9200))
        self.user = os.environ.get("ES_USER", "elastic")
        self.password = os.environ.get("ES_PASSWORD", "infini_rag_flow_es")
        
        self.client = Elasticsearch(
            f"http://{self.host}:{self.port}",
            basic_auth=(self.user, self.password)
        )
        try:
            info = self.client.info()
            logger.info(f"Connected to Elasticsearch: {info['version']['number']}")
        except Exception as e:
            logger.error(f"Failed to connect to Elasticsearch: {e}")

    def insert(self, index_name: str, documents: list):
        """Bulk insert documents to an isolated tenant index."""
        # 1. Ensure index exists with a basic mapping (supporting 1536 dim vectors)
        if not self.client.indices.exists(index=index_name):
            mapping = {
                "mappings": {
                    "properties": {
                        "content": {"type": "text"},
                        "doc_id": {"type": "keyword"},
                        "kb_id": {"type": "keyword"},
                        "tenant_id": {"type": "keyword"},
                        "q_1536_vec": {
                            "type": "dense_vector",
                            "dims": 1536,
                            "index": True,
                            "similarity": "cosine"
                        }
                    }
                }
            }
            self.client.indices.create(index=index_name, body=mapping)
            logger.info(f"Created Elasticsearch index: {index_name}")

        # 2. Prepare bulk insert actions
        actions = []
        for doc in documents:
            action = {
                "_index": index_name,
                "_source": doc
            }
            # Use doc["_id"] if it exists to overwrite
            if "_id" in doc:
                action["_id"] = doc.pop("_id")
            actions.append(action)

        # 3. Execute bulk insert
        success, _ = bulk(self.client, actions)
        logger.info(f"Successfully inserted {success} chunks into index {index_name}")
        return success

docStoreConn = ElasticsearchConnection()
