from minio_storage import _cliente, SILVER_BUCKET

cliente = _cliente()

print("Bucket Silver:", SILVER_BUCKET)

paginador = cliente.get_paginator("list_objects_v2")

for pagina in paginador.paginate(Bucket=SILVER_BUCKET):
    for objeto in pagina.get("Contents", []):
        print(repr(objeto["Key"]))