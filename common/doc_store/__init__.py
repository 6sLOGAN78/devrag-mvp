import os
from common.doc_store.es_conn_base import docStoreConn as es_conn

# -------------------------------------------------------------
# CHANGE: RAGFlow DB Abstraction Factory Layer
# -------------------------------------------------------------
# In a full RAGFlow system, this reads from service_conf.yaml 
# to determine if it should route to Infinity, ES, or Milvus.
DOC_STORE_TYPE = os.environ.get("DOC_STORE_TYPE", "elasticsearch")

def get_doc_store_conn():
    if DOC_STORE_TYPE == "elasticsearch":
        return es_conn
    # elif DOC_STORE_TYPE == "infinity":
    #     from common.doc_store.infinity_conn import docStoreConn as infinity_conn
    #     return infinity_conn
    else:
        raise NotImplementedError(f"Doc store {DOC_STORE_TYPE} is not yet implemented.")

docStoreConn = get_doc_store_conn()
