from qdrant_client.models import Prefetch,SparseVector, Fusion, FusionQuery

def busca_hibrida_qdrant(client_qdrant,collection,dense,sparse, limit=50, filtro=None):
    sparse_query = SparseVector(
        indices=[int(k) for k in sparse.keys()],
        values=[float(v) for v in sparse.values()],
    )

    prefetch = [
        Prefetch(
            query=dense.tolist(),
            using="dense",
            limit=limit,
            filter=filtro
        ),
        Prefetch(
            query=sparse_query,
            using="sparse",
            limit=limit,
            filter=filtro
        )
    ]

    results = client_qdrant.query_points(
        collection_name=collection,
        prefetch=prefetch,
        query=FusionQuery(
            fusion=Fusion.RRF
        ),
        limit=limit,
        with_payload=True
    )
    return results.points