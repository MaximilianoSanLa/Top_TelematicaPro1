# datanode_server.py
import os
import socket
import hashlib
from pathlib import Path
from concurrent import futures
import grpc

import data_node_pb2 as pb
import data_node_pb2_grpc as pb_grpc

# ===================== Configuración =====================
ROOT_DIR   = Path("/home/ec2-user/worker_data")
TMP_DIR    = ROOT_DIR / "tmp"#directorio temporal
BLOCKS_DIR = ROOT_DIR #directorio de bloques
READ_CHUNK = 1 * 1024 * 1024  # 1 MB para servir descargas

# Opcional: token mínimo. Deja en None para desactivar auth.
REQUIRED_TOKEN = None  # ej: "secreto-123"

def _get_file_dirs(file_name: str):
    """Crea directorios específicos para un archivo"""
    safe_name = file_name
    print(f"Safe name: {safe_name}")
    file_tmp_dir = TMP_DIR / safe_name
    file_blocks_dir = BLOCKS_DIR / safe_name
    file_tmp_dir.mkdir(parents=True, exist_ok=True)
    file_blocks_dir.mkdir(parents=True, exist_ok=True)
    return file_tmp_dir, file_blocks_dir

def _ensure_dirs():
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    BLOCKS_DIR.mkdir(parents=True, exist_ok=True)

# def _extract_bearer_token(context) -> str | None:
#     """Lee 'authorization: Bearer <token>' de metadata (si llega)."""
#     md = dict(context.invocation_metadata())
#     auth = md.get("authorization")
#     if not auth:
#         return None
#     if auth.lower().startswith("bearer "):
#         auth = auth.split(" ", 1)
#         return auth[1]
#     return auth

# def _check_auth(context):
#     if REQUIRED_TOKEN is None:
#         return
#     tok = _extract_bearer_token(context)
#     if tok != REQUIRED_TOKEN:
#         context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid token")

# ===================== Servicer =====================
class DataNodeServicer(pb_grpc.DataNodeServicer):
    def UploadBlock(self, request_iterator: pb.UploadBlockRequest, context: grpc.ServicerContext):
        """
        Flujo: START (abre .part) -> CHUNK... -> COMMIT (verifica y renombra .part -> .blk).
        """
        #_check_auth(context)
        _ensure_dirs()

        started = False
        committed = False
        block_id = None
        tmp_path: Path | None = None
        out = None  # file handle
        hasher = hashlib.sha256()
        written = 0

        try:
            for msg in request_iterator:
                if msg.WhichOneof("msg") == "start":
                    if started:
                        context.abort(grpc.StatusCode.ALREADY_EXISTS, "este chunk ya se inicio")
                    if not msg.start.block_id:
                        context.abort(grpc.StatusCode.INVALID_ARGUMENT, "block_id required")
                    
                    block_id = msg.start.block_id
                    file_name = msg.start.file_name
                    print(f"File name: {file_name}")
                    file_tmp_dir, file_blocks_dir = _get_file_dirs(file_name)
                    print(f"[DataNode] 📂 Directorios creados: {file_tmp_dir}, {file_blocks_dir}")
                    tmp_path = file_tmp_dir / f"{block_id}.part"
                    # Abre el archivo temporal para este bloque (overwrite)
                    out = tmp_path.open("wb")
                    started = True
                    print(f"[DataNode] ✅ Iniciado recepción del bloque {block_id}")

                elif msg.WhichOneof("msg") == "chunk":
                    if not started:
                        context.abort(grpc.StatusCode.FAILED_PRECONDITION, "no se inicio el chunk")
                    data = msg.chunk.data
                    if data:
                        out.write(data)
                        hasher.update(data)
                        written += len(data)
                        # Progreso cada 10MB
                        if written % (10 * 1024 * 1024) == 0:
                            print(f"[DataNode] 📥 Recibido {written // (1024*1024)} MB del bloque {block_id}")

                elif msg.WhichOneof("msg") == "commit":
                    if not started:
                        context.abort(grpc.StatusCode.FAILED_PRECONDITION, "no se inicio el chunk")
                    if out:
                        out.flush()#vacia el buffer
                        out.close()#cierra el archivo
                        out = None#limpia el archivo

                    expected_size = int(msg.commit.expected_size or 0)
                    given_sha = (msg.commit.sha256 or "").lower()

                    # Verifica tamaño
                    if expected_size and expected_size != written:
                        # Limpia el temporal si hay inconsistencia
                        try:
                            if tmp_path and tmp_path.exists():
                                tmp_path.unlink()
                        finally:
                            context.abort(
                                grpc.StatusCode.DATA_LOSS,
                                f"size mismatch: expected {expected_size}, got {written}"
                            )

                    # Verifica hash
                    computed = hasher.hexdigest()
                    if given_sha and given_sha.lower() != computed:
                        try:
                            if tmp_path and tmp_path.exists():
                                tmp_path.unlink()
                        finally:
                            context.abort(
                                grpc.StatusCode.DATA_LOSS,
                                "sha256 mismatch"
                            )

                    # Finaliza (rename atómico)
                    final_path = file_blocks_dir / f"{block_id}.blk"
                    if msg.commit.finalize:
                        os.replace(tmp_path, final_path)  # atómico en mismo FS
                        print(f"[DataNode] 💾 BLOQUE GUARDADO: {block_id} ({written} bytes) → {final_path}")
                    committed = True

                    print(f"[DataNode] ✅ CONFIRMACIÓN: Bloque {block_id} procesado exitosamente")
                    return pb.UploadBlockResult(
                        ok=True,
                        error="",
                        stored_size=written,
                        block_path=str(final_path if msg.commit.finalize else tmp_path)
                    )

            # Si terminó el stream sin COMMIT explícito
            if not committed:
                if out:
                    out.close()
                if tmp_path and tmp_path.exists():
                    tmp_path.unlink(missing_ok=True)
                context.abort(grpc.StatusCode.FAILED_PRECONDITION, "commit not received")

        finally:
            if out:
                out.close()

    def DownloadBlock(self, request: pb.DownloadBlockRequest, context: grpc.ServicerContext):
        #_check_auth(context)
        _ensure_dirs()

        block_id = request.block_id
        if not block_id:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "block_id required")

        final_path = BLOCKS_DIR / f"{block_id}.blk"
        if not final_path.exists():
            context.abort(grpc.StatusCode.NOT_FOUND, "block not found")

        offset = int(request.offset or 0)
        length = int(request.length or 0)

        size = final_path.stat().st_size
        if offset < 0 or offset > size:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "invalid offset")

        remaining = (size - offset) if length == 0 else min(length, size - offset)
        
        print(f"[DataNode] 📤 Iniciando envío del bloque {block_id} ({remaining} bytes)")
        if offset > 0:
            print(f"[DataNode] 📍 Enviando desde offset {offset}")

        sent_bytes = 0
        with final_path.open("rb") as f:
            f.seek(offset)
            while remaining > 0:
                n = min(READ_CHUNK, remaining)
                data = f.read(n)
                if not data:
                    break
                remaining -= len(data)
                sent_bytes += len(data)
                
                # Progreso cada 10MB enviados
                if sent_bytes % (10 * 1024 * 1024) == 0:
                    print(f"[DataNode] 📤 Enviado {sent_bytes // (1024*1024)} MB del bloque {block_id}")
                
                yield pb.DataChunk(data=data)
        
        print(f"[DataNode] ✅ ENVÍO COMPLETADO: Bloque {block_id} enviado exitosamente ({sent_bytes} bytes)")

    def DeleteBlock(self, request, context):
        #_check_auth(context)
        _ensure_dirs()

        block_id = request.block_id
        if not block_id:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "block_id required")
        final_path = BLOCKS_DIR / f"{block_id}.blk"
        if not final_path.exists():
            context.abort(grpc.StatusCode.NOT_FOUND, "block not found")
        final_path.unlink()
        return pb.Ack(ok=True, error="")

    def Health(self, request, context):
        return pb.HealthResponse(
            ok=True,
            node=socket.gethostname(),
            version="1.0"
        )

# ===================== Arranque =====================
def serve(port: int = 5002):
    _ensure_dirs()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    pb_grpc.add_DataNodeServicer_to_server(DataNodeServicer(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    print(f"DataNode gRPC escuchando en :{port}")
    server.wait_for_termination()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="DataNode (gRPC) – bloques")
    parser.add_argument("--port", type=int, default=5002)
    args = parser.parse_args()
    serve(args.port)
