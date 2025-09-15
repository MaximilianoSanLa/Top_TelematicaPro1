from utilsClient import dividir_bloque
import argparse
import json
import os
import shutil
import time
import hashlib
import uuid
from pathlib import Path
import grpc
import requests
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
def _upload_block_to_one_datanode(dn_addr: str, block_id: str, block_path: Path, expected_size: int, sha256: str, file_name: str, auth_token=None):
    print(f"DEBUG: file_name = {file_name}")
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
                    sha256="",
                    file_name=file_name  # ✅ AGREGAR ESTA LÍNEA
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

    # ✅ AGREGAR ESTA LÍNEA
    file_name = remote_path

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
        _upload_block_to_one_datanode(dn_addr, id, path, size, hash, file_name, auth_token)

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


def _download_block_from_datanode(dn_addr: str, block_id: str, output_path: Path, auth_token: str | None = None):
    """
    Descarga un bloque específico desde un DataNode y lo guarda en output_path.
    """
    if auth_token is not None:
        metadata = [('authorization', f'Bearer {auth_token}')]
    else:
        metadata = None
    
    print(f"🔍 Intentando conectar con DataNode: {dn_addr}")
    print(f"📥 Buscando bloque {block_id} en DN: {dn_addr}")
    
    try:
        with grpc.insecure_channel(dn_addr) as channel:
            stub = dnpb_grpc.DataNodeStub(channel)
            request = dnpb.DownloadBlockRequest(
                block_id=block_id,
                offset=0,    # Descargar desde el inicio
                length=0     # Descargar todo el bloque (0 = completo)
            )
            
            print(f"✅ CONEXIÓN EXITOSA con DataNode: {dn_addr}")
            print(f"📡 Iniciando descarga del bloque {block_id}...")
            
            with output_path.open('wb') as f:
                total_downloaded = 0
                for chunk in stub.DownloadBlock(request, metadata=metadata):
                    data = chunk.data
                    if data:
                        f.write(data)
                        total_downloaded += len(data)
                        
                        # Progreso cada 10MB
                        if total_downloaded % (10 * 1024 * 1024) == 0:
                            print(f"📥 Descargado {total_downloaded // (1024*1024)} MB del bloque {block_id} desde {dn_addr}")
            
            print(f"🎉 DESCARGA EXITOSA desde {dn_addr}: Bloque {block_id} ({total_downloaded} bytes) → {output_path}")
            return total_downloaded
            
    except grpc.RpcError as e:
        print(f"❌ ERROR DE CONEXIÓN con DataNode {dn_addr}: {e}")
        print(f"❌ No se pudo obtener el bloque {block_id} desde {dn_addr}")
        # Limpiar archivo parcial si existe
        if output_path.exists():
            output_path.unlink()
        raise
    except Exception as e:
        print(f"❌ ERROR INESPERADO conectando a {dn_addr}: {e}")
        # Limpiar archivo parcial si existe
        if output_path.exists():
            output_path.unlink()
        raise


def download_block(dn_addr: str, block_id: str, out_path: str,
                   offset: int = 0, length: int = 0, auth_token: str | None = None) -> int:
    """
    Descarga un bloque completo (o un rango) desde un DataNode y lo guarda en disco.
    Devuelve los bytes escritos.
    """
    metadata = [('authorization', f'Bearer {auth_token}')] if auth_token else None
    written = 0
    out = Path(out_path)
    with grpc.insecure_channel(dn_addr) as channel:
        stub = dnpb_grpc.DataNodeStub(channel)
        stream = stub.DownloadBlock(
            dnpb.DownloadBlockRequest(block_id=block_id, offset=offset, length=length),
            metadata=metadata
        )
        with out.open('wb') as f:
            for chunk in stream:          # server-streaming de DataChunk{ bytes data }
                f.write(chunk.data)
                written += len(chunk.data)
    return written


if __name__ == "__main__":
    import sys
    BASE_URL = "http://44.217.41.36:3000"
    while True:
        print("Ingresa 1 para ingresar a tu cuenta.\n Ingresa 2 para crear cuenta")
        
        if(input()=="1"):
            print("Ingresa Usuario: ")
            user= input()
            print("Ingresa Contrasena: ")
            contrasena= input()
            payload = {
                "username": user,
                "password": contrasena
            }
            response = requests.post(f"{BASE_URL}/login", json=payload)
            if response.status_code == 200:
               data = response.json()
               print("Login successful!")
               print("Auth Key:", data["authKey"])
            else:
               print("Login failed:", response.status_code, response.text)
               break 
        else:
            print("Ingresa Usuario: ")
            user= input()
            print("Ingresa Contrasena: ")
            contrasena= input()
            payload = {
                "superKey": "my-secret-superuser-key",
                "username": user,
                "password": contrasena
            }
            response = requests.post(f"{BASE_URL}/login", json=payload)
        elecion= input("Utilize nuestra api: get 'Archivo', put 'Archivo', ls, mkdir 'Nombre',rm 'Archivo' ")
        eleciones = elecion.split()
        authKey = response.json()["authKey"]
        print("🔑 AuthKey:", authKey)
        cmd_payload = {
           "authKey": authKey,
            "cmd": "ls"   # list files
        }

        print(eleciones[0])
        if eleciones[0] == "get":
            # Modo descarga
            print("🔽 Modo DESCARGA")

            # Ejemplo: python Client.py download Archivo128MBOut/manifest.json archivo_descargado.txt
            if len(sys.argv) >= 4:
                manifest_path = sys.argv[2]
                output_file = sys.argv[3]
            else:
                manifest_path = "Archivo128MBOut/manifest.json"
                output_file = "archivo_descargado.txt"
            output_file=eleciones[1]

            try:
                with open(manifest_path, "r") as f:
                    manifest = json.load(f)

                # Crear carpeta para bloques descargados
                download_blocks_dir = Path("DownloadedBlocks")
                download_blocks_dir.mkdir(exist_ok=True)
                print(f"📁 Creando directorio de bloques: {download_blocks_dir}")
                cmd_res = requests.post(f"{BASE_URL}/command", json=cmd_payload)

                results = data.get("results", [])
                #dataNodes = ["localhost:5002", "localhost:5002", "localhost:5002"]
                dataNodes = [f"{r['worker']}:5002" for r in results if "worker" in r]

                # Remove duplicates
                dataNodes = list(set(dataNodes))
                # Lista de DataNodes disponibles
                
                downloaded_blocks = []

                # Procesar cada bloque del manifest
                for block_info in manifest["blocks"]:
                    block_id = block_info["id"]
                    block_index = int(block_info["index"])
                    expected_size = int(block_info["size"])

                    # Seleccionar DataNode (por ahora usar el índice para rotar entre DataNodes)
                    datanode_idx = block_index % len(dataNodes)
                    dn_addr = dataNodes[datanode_idx]

                    # Crear archivo .block individual
                    block_filename = f"block_{block_index:06d}_{block_id[:8]}.block"
                    block_path = download_blocks_dir / block_filename

                    print(f"\n🔽 Descargando bloque {block_index} desde {dn_addr}")
                    print(f"   📦 ID: {block_id}")
                    print(f"   📏 Tamaño esperado: {expected_size} bytes")

                    result = download_block(
                        dn_addr=dn_addr,
                        block_id=block_id,
                        out_path=str(block_path),
                        auth_token=None
                    )

                    # Verificar tamaño descargado
                    if result != expected_size:
                        print(f"⚠️ Advertencia: Tamaño descargado {result} != esperado {expected_size}")

                    downloaded_blocks.append((block_index, block_path, result))
                    print(f"✅ Bloque guardado: {block_path} ({result} bytes)")

                # Crear archivo final concatenado
                print(f"\n🔗 Concatenando bloques en archivo final: {output_file}")
                with open(output_file, "wb") as final_file:
                    total_bytes = 0
                    for block_index, block_path, size in sorted(downloaded_blocks):
                        with open(block_path, "rb") as block_file:
                            data = block_file.read()
                            final_file.write(data)
                            total_bytes += len(data)
                            print(f"✅ Bloque {block_index} concatenado: {len(data)} bytes")

                print(f"\n🎉 Descarga completada:")
                print(f"   📄 Archivo final: {output_file} ({total_bytes} bytes)")
                print(f"   📁 Bloques individuales en: {download_blocks_dir}/")
                for block_index, block_path, size in sorted(downloaded_blocks):
                    print(f"      📦 {block_path.name} ({size} bytes)")

            except Exception as e:
                print(f"❌ Error en descarga: {e}")

        elif eleciones[0]=="put":
            # Modo subida (por defecto)
            fileAndKey= authKey+"/"+eleciones[1]
            print(fileAndKey)
            print(eleciones)
            print("🔼 Modo SUBIDA")
            mf = put_file_with_local_blocks(
                file_path="c:/Users/maxim/Downloads/grpc/Top_TelematicaPro1/Client/Archivo128MB.txt",
                remote_path=fileAndKey,
                # namenode_addr="localhost:50051",
                namenode_addr="44.217.41.36:50051",
                auth_token=None  # o tu token
            )
            print(json.dumps(mf, indent=2))
        elif eleciones[0]=="ls":
            cmd_res = requests.post(f"{BASE_URL}/command", json=cmd_payload)
            data = cmd_res.json()
            if cmd_res.status_code == 200:
                print("📂 Command:", data["cmd"])
                print("📜 Results:")
                for result in data["results"]:
                    print(result)
            else:
                print("❌ Command failed:", cmd_res.text)
