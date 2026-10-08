"""Elasticsearch index settings and dynamic templates (plan 03-08, IDX-06, IDX-08).

Derived from the reference ``conf/mapping.json`` with one deliberate change: the four fixed-dimension vector
templates (512, 768, 1024 and 1536 dims) are removed. A dataset's vector field is added on demand by :func:`vector_mapping`, so one tenant index can carry any
embedding dimension from 1 to 4096 (``docs/05-rag-pipeline/indexing.md``: ``q_{dim}_vec``, cosine, HNSW).
"""
from __future__ import annotations

from typing import Any

INDEX_SETTINGS: dict[str, Any] = {
    "index": {"number_of_shards": 1, "number_of_replicas": 0, "refresh_interval": "1000ms"},
    "similarity": {
        "scripted_sim": {
            "type": "scripted",
            "script": {
                "source": (
                    "double idf = Math.log(1+(field.docCount-term.docFreq+0.5)/(term.docFreq + 0.5))/Math.log(1+((field.docCount-0.5)/1.5));"
                    " return query.boost * idf * Math.min(doc.freq, 1);"
                )
            },
        }
    },
}

INDEX_MAPPINGS: dict[str, Any] = {
    "properties": {"lat_lon": {"type": "geo_point", "store": "true"}},
    "date_detection": "true",
    "dynamic_templates": [
        {"int": {"match": "*_int", "mapping": {"type": "integer", "store": "true"}}},
        {"ulong": {"match": "*_ulong", "mapping": {"type": "unsigned_long", "store": "true"}}},
        {"long": {"match": "*_long", "mapping": {"type": "long", "store": "true"}}},
        {"short": {"match": "*_short", "mapping": {"type": "short", "store": "true"}}},
        {"numeric": {"match": "*_flt", "mapping": {"type": "float", "store": True}}},
        {"tks": {"match": "*_tks", "mapping": {"type": "text", "similarity": "scripted_sim", "analyzer": "whitespace", "store": True}}},
        {"ltks": {"match": "*_ltks", "mapping": {"type": "text", "analyzer": "whitespace", "store": True}}},
        {
            "kwd": {
                "match_pattern": "regex",
                "match": "^(.*_(kwd|id|ids|uid|uids)|uid|id)$",
                "mapping": {"type": "keyword", "similarity": "boolean", "store": True},
            }
        },
        {
            "dt": {
                "match_pattern": "regex",
                "match": "^.*(_dt|_time|_at)$",
                "mapping": {"type": "date", "format": "yyyy-MM-dd HH:mm:ss||yyyy-MM-dd||yyyy-MM-dd_HH:mm:ss", "store": True},
            }
        },
        {"nested": {"match": "*_nst", "mapping": {"type": "nested"}}},
        {"object": {"match": "*_obj", "mapping": {"type": "object", "dynamic": "true"}}},
        {
            "string": {
                "match_pattern": "regex",
                "match": "^.*_(with_weight|list)$",
                "mapping": {"type": "text", "index": "false", "store": True},
            }
        },
        {"rank_feature": {"match": "*_fea", "mapping": {"type": "rank_feature"}}},
        {"rank_features": {"match": "*_feas", "mapping": {"type": "rank_features"}}},
        {"binary": {"match": "*_bin", "mapping": {"type": "binary"}}},
    ],
}


def vector_mapping(dim: int) -> dict[str, Any]:
    """Body of one ``q_{dim}_vec`` field: dense_vector, cosine, HNSW m=16 and ef_construction=200."""
    return {
        "type": "dense_vector",
        "dims": dim,
        "index": True,
        "similarity": "cosine",
        "index_options": {"type": "hnsw", "m": 16, "ef_construction": 200},
    }
