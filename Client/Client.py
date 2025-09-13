from utilsClient import dividir_bloque, limpiar_archivos_temporales, limpiar_todo
import argparse
import json
import os
import shutil
import time
import hashlib
import uuid
from pathlib import Path
import grpc

import name_node_pb2 as pb
import name_node_pb2_grpc as pb_grpc
import data_node_pb2 as dnpb
import data_node_pb2_grpc as dnpb_grpc

CHUNK_SIZE = 1 * 1024 * 1024  # 1 MB


def plan_write(namenode_addr: str, file_path: str)->pb.PlanFileWriteResponse:
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(p)

    file_size = p.stat().st_size

    with grpc.insecure_channel(namenode_addr) as channel:
        stub = pb_grpc.NameNodeStub(channel)
        resp = stub.PlanFileWrite(pb.PlanFileWriteRequest(
            file_name=p.name,
            file_size=file_size
        ))

    print(f"NameNode → block_size={resp.block_size} bytes, num_blocks={resp.num_blocks}")
    for a in resp.assignments:
        print(f"  - block {a.block_index}: {list(a.datanodes)}")
    return resp 

def file_sha256(path:Path)->str:
    h=hashlib.sha256()
    with open(path, "rb") as file:
        while True:
            data=file.read(1024*1024)
            if not data:
                break
            h.update(data)
    return h.hexdigest()
def _upload_block_to_one_datanode(dn_addr: str, block_id: str, block_path: Path, expected_size: int, sha256: str, auth_token=None):
    block_path=Path(block_path)
    if auth_token is not None:
        metadata = [('authorization', f'Bearer {auth_token}')] 
    else:
        metadata = None
    def _create_upload_requests():
        try:
            print(f"DEBUG: Iniciando upload - block_id={block_id}, expected_size={expected_size}, block_path={block_path}")
            # 1) start
            yield dnpb.UploadBlockRequest(
                start=dnpb.UploadBlockStart(
                    block_id=block_id,
                    expected_size=expected_size,   
                    sha256=""                     
                )
            )
            print("DEBUG: START message enviado")
            # 2) chunks
            with block_path.open('rb') as f: # Abre el archivo en modo binario de lectura
                sent = 0# Contador de bytes ya enviados
                print(f"DEBUG: Iniciando lectura de archivo, expected_size={expected_size}")
                while sent < expected_size: # Mientras no se haya enviado el tamaño esperado
                    to_read = min(CHUNK_SIZE, expected_size - sent)
                    data = f.read(to_read) # Lee el tamaño del chunk
                    if not data:
                        print("DEBUG: No más datos para leer")
                        break
                    sent += len(data) # Actualiza el contador de bytes ya enviados
                    print(f"DEBUG: Enviando chunk de {len(data)} bytes, total enviado: {sent}")
                    yield dnpb.UploadBlockRequest(
                        chunk=dnpb.DataChunk(data=data) # Envía el chunk
                    )
            # 3) commit (finalize)
            print("DEBUG: Enviando COMMIT message")
            yield dnpb.UploadBlockRequest(
                commit=dnpb.UploadBlockCommit(
                    expected_size=expected_size,
                    sha256=sha256,
                    finalize=True
                )
            )
            print("DEBUG: COMMIT message enviado")
        except Exception as e:
            print(f"DEBUG: Error en generador: {e}")
            raise
        # Ejecuta el stream
    with grpc.insecure_channel(dn_addr) as channel: # Crea un canal de comunicación con el DataNode
        stub = dnpb_grpc.DataNodeStub(channel) # Crea un stub para el DataNode
        result = stub.UploadBlock(_create_upload_requests(), metadata=metadata) # Ejecuta el stream
        if not result.ok: # Si el resultado no es ok, lanza un error
            raise RuntimeError(f"DataNode {dn_addr} rechazó el bloque {block_id}: {result.error}")
        return result # Retorna el resultado
def put_file_with_local_blocks(file_path: str, remote_path: str, namenode_addr: str, auth_token: str | None = None):
    """
    Flujo completo:
      1) PlanFileWrite (NameNode)
      2) dividir_bloque (usa el block_size del plan; genera manifest y .bin locales)
      3) Por cada bloque del manifest, para cada réplica del plan:
           UploadBlock(start/chunk/commit) a ese DataNode gRPC
      4) Devuelve un manifest lógico listo para RegisterFile
    """
    # 1) Plan con NameNode
    plan = plan_write(namenode_addr, file_path)
    print(f"DEBUG: plan = {plan}")
    block_size = int(plan.block_size)
    num_blocks_plan = int(plan.num_blocks)

    # 2) Dividir en bloques locales usando el block_size del plan
    manifest_path = dividir_bloque(file_path, block_size)#Genera el manifest
    manifest = json.loads(Path(manifest_path).read_text(encoding='utf-8'))#Contiene la informacion de los bloques 

    # Validación simple
    if len(manifest["blocks"]) != num_blocks_plan:
        print(f"⚠️ Aviso: manifest tiene {len(manifest['blocks'])} bloques, plan esperaba {num_blocks_plan}. (Último bloque puede ajustar)")

    # 3) Subir bloques (UN DataNode por bloque)
    blocks_for_register = []
    for block in manifest["blocks"]:
        order=int(block["index"]) #Orden del bloque
        id=block["id"]
        size=int(block["size"])
        hash=block["hash"]
        path=block["path"]
    
        Assign=None
        for a in plan.assignments:
            if a.block_index==order:
                Assign=a
                break
        if Assign is None:
            raise ValueError(f"No se encontró el bloque {order} en el plan")
        if len(Assign.datanodes) == 0:
            raise RuntimeError(f"No hay DataNode asignado para el bloque {order}")
        dn_addr = Assign.datanodes[0]
        print(f"DEBUG: dn_addr = '{dn_addr}', type = {type(dn_addr)}")

        print(f"⬆️  Subiendo bloque {order} ({size} B) → DN: {dn_addr}")
        _upload_block_to_one_datanode(dn_addr, id, path, size, hash, auth_token)

        blocks_for_register.append({
            "order": order,
            "block_id": id,
            "size": size,
            "sha256": hash,
            "replica": dn_addr  # puedes dejar 'replicas': [dn_addr] si prefieres
        })

    logical_manifest = {
        "path": remote_path,
        "file_size": int(Path(file_path).stat().st_size),
        "block_size": block_size,
        "blocks": blocks_for_register
    }

    print("✅ Subida completada (sin réplicas). Manifest para RegisterFile listo.")
    return logical_manifest

    


if __name__ == "__main__":
    # Ejemplo de uso:
    mf = put_file_with_local_blocks(
        file_path="Archivo128MB.txt",
        remote_path="/users/camilo/Archivo128MB.txt",
        namenode_addr="localhost:50051",
        auth_token=None  # o tu token
    )
    print(json.dumps(mf, indent=2))
