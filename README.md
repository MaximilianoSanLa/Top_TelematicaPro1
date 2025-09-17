## GridDFS — Sistema de Archivos Distribuido (DFS)

## Descripción
Sistema de archivos distribuido estilo HDFS con separación de metadatos y datos:
- NameNode: planifica la escritura (tamaño de bloque, número de bloques, distribución).
- DataNode(s): almacenan y sirven bloques.
- Cliente: sube/descarga archivos mediante gRPC streaming.
- API Node opcional: facilita listados remotos para el modo descarga.

## Requisitos
- Python 3.10+
- Node.js 18+ (solo si usas `node-api`/`node-worker`)
- pip y virtualenv recomendados

Paquetes Python:
- grpcio
- grpcio-tools
- protobuf
- requests

Instalación rápida:
```bash
python -m venv .venv
. .venv/Scripts/activate    # Windows PowerShell
# source .venv/bin/activate # Linux/macOS
pip install grpcio grpcio-tools protobuf requests
```

## Estructura del proyecto
```text
Top_TelematicaPro1/
  Client/
    Client.py
    utilsClient.py
    data_node.proto
    name_node.proto
    Archivo128MB.txt
    Archivo128MBOut/
      blocks/
      manifest.json
      temp/
    DownloadedBlocks/          # se crea en tiempo de ejecución
  DataNode/
    DataNode.py                # servidor DataNode gRPC
    DataNode2.py, DataNode3.py # variantes opcionales
    data/
      blocks/<archivo>/*.blk   # almacenamiento final de bloques
      tmp/<archivo>/           # temporales
    data_node.proto
  NameNode/
    NameNode.py                # servidor NameNode gRPC
  node-api/
    api.js                     # API HTTP auxiliar (listados)
  node-worker/
    worker.js                  # agente que ejecuta "ls" en workers
  config/
    server-properties
  README.md
```

## Configuración
- NameNode:
  - `NameNode/NameNode.py`
    - `BLOCK_SIZE = 64 * 1024 * 1024` (64 MiB)
    - `DATANODES = ["host1:5002", "host2:5002", ...]`  Ajusta a tus nodos reales.
- DataNode:
  - `DataNode/DataNode.py` escucha por defecto en `:5002`.
  - Directorios de datos: `DataNode/data/blocks` y `DataNode/data/tmp`.
- Puertos por defecto:
  - NameNode: `50051`
  - DataNode(s): `5002`
- Replicación:
  - El NameNode actual devuelve 1 dirección por bloque (R=1, round‑robin). Para R>1, extiende la lista `datanodes` por bloque en el NameNode y ajusta el cliente para subir a todas las réplicas.

## Compilación de .proto (si necesitas regenerar stubs)
Desde la raíz del repo:
```bash
python -m grpc_tools.protoc -I Client --python_out=Client --grpc_python_out=Client Client/name_node.proto
python -m grpc_tools.protoc -I Client --python_out=Client --grpc_python_out=Client Client/data_node.proto
python -m grpc_tools.protoc -I DataNode --python_out=DataNode --grpc_python_out=DataNode DataNode/data_node.proto
```

## Ejecución

### 1) Iniciar NameNode
```bash
python NameNode/NameNode.py
```
- Escucha en `:50051`.

### 2) Iniciar DataNode(s)
En cada máquina/worker donde guardarás bloques:
```bash
python DataNode/DataNode.py
```
- Abre el puerto `5002` en firewall.
- Verifica que `NameNode/NameNode.py` tenga sus direcciones reales en `DATANODES`.

### 3) (Opcional) API Node y Worker
```bash
cd node-worker && npm install && node worker.js
cd ../node-api && npm install && node api.js
```

### 4) Cliente
Comandos disponibles en `Client/Client.py`: `put <archivo>`, `get <archivo>`, `ls`.

Ejemplos:
```bash
python Client/Client.py
# En el menú interactivo:
# put Archivo128MB.txt
# get Archivo128MB.txt
# ls
```

Notas:
- Subida (put): el cliente divide el archivo local en bloques de 64 MiB y los sube por streaming gRPC al DataNode asignado por el NameNode.
- Descarga (get): el cliente consulta los workers mediante la API HTTP para encontrar `*.blk` del archivo, descarga cada bloque y concatena en el archivo final.
- Los bloques descargados se guardan en `Client/DownloadedBlocks/` y luego se integran respetando `block_index`.

## Lógica de partición (resumen)
- Tamaño de bloque: `BLOCK_SIZE = 64 * 1024 * 1024`.
- Bucle:
  - `SizeBloque = min(ArchivoFaltante, BLOCK_SIZE)`.
  - Leer en trozos de `ChunkSize = 1 MiB` hasta completar `SizeBloque`.
  - Actualizar `ArchivoFaltante` y `block_index`.
- Garantías:
  - Bloques de tamaño fijo salvo el último (`≤ BLOCK_SIZE`).
  - Suma de tamaños de bloques = tamaño del archivo original.

## Lógica de distribución (resumen)
- NameNode (round‑robin, R=1):
  - Para bloque `i`: `DATANODES[i % M]` donde `M = len(DATANODES)`.
- Extensión a replicación R>1:
  - Para bloque `i`: `R` nodos distintos `DATANODES[(i + k) % M]` para `k=0..R-1`.
  - El cliente debe subir a todas las réplicas y manejar confirmaciones/reintentos.

## Estructura de almacenamiento
- Servidor:
  - `DataNode/data/blocks/<archivo>/*.blk`  bloques finales.
  - `DataNode/data/tmp/<archivo>/`           temporales de escritura.
- Cliente:
  - `Client/<NombreArchivo>Out/blocks/*.bin`  bloques locales pre‑subida.
  - `Client/<NombreArchivo>Out/manifest.json` metadatos locales.
  - `Client/DownloadedBlocks/`                bloques descargados.

## Pruebas rápidas
- Subida:
  1) Inicia NameNode y DataNodes.
  2) Ejecuta `put Archivo128MB.txt`.
  3) Verifica `DataNode/data/blocks/Archivo128MB.txt/*.blk`.
- Descarga:
  1) Ejecuta `get Archivo128MB.txt`.
  2) Verifica `Client/DownloadedBlocks/` y el archivo final.
  3) Compara tamaño con el original.

## Solución de problemas
- No descarga bloques, `grouped_ids` vacío:
  - Normaliza directorios en el cliente: compara `current_dir.removeprefix("./")` con `target_dir.removeprefix("./")` y elimina `:` finales.
- Conexión rechazada a DataNode:
  - Usa siempre `host:5002`. Verifica firewall/puerto y reachability.
- Bloques incompletos:
  - Revisa que el stream haga `commit(finalize=true)` y que `ChunkSize` sea coherente.

## Limitaciones actuales
- Replicación efectiva R=1.
- Descubrimiento de bloques en GET depende del `node-api`/`node-worker` y del formato de `ls`.
- Checksums por bloque modelados en proto, pero verificación en descarga puede activarse/mejorarse.

## Licencia
Indica aquí la licencia del proyecto si aplica.
