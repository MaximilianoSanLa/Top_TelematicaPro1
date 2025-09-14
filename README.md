# Sistema de Archivos Distribuido (DFS)

Un sistema de archivos distribuido implementado en Python usando gRPC, inspirado en HDFS. Permite almacenar archivos grandes dividiéndolos en bloques y distribuyéndolos entre múltiples DataNodes.

## 🏗️ Arquitectura

```
Cliente ──→ NameNode (puerto 50051) ──→ Plan de distribución
   ↓
DataNodes (puerto 5002+) ──→ Almacenamiento de bloques
```

### Componentes:

- **NameNode**: Coordinador central que maneja metadatos y asignación de bloques
- **DataNode**: Nodos de almacenamiento que guardan los bloques físicos
- **Cliente**: Interfaz para subir archivos al sistema distribuido

## 🚀 Instalación

### Dependencias

```bash
pip install grpcio grpcio-tools pathlib
```

### Generación de archivos protobuf (si es necesario)

```bash
# Para NameNode
python -m grpc_tools.protoc --python_out=. --grpc_python_out=. name_node.proto

# Para DataNode
python -m grpc_tools.protoc --python_out=. --grpc_python_out=. data_node.proto
```

## ▶️ Ejecución

### Orden de inicio (IMPORTANTE):

#### 1. Iniciar NameNode
```bash
cd NameNode
python NameNode.py
```
**Salida esperada:**
```
NameNode gRPC escuchando en :50051
```

#### 2. Iniciar DataNode(s)
```bash
cd DataNode
python DataNode.py
```
**Salida esperada:**
```
DataNode gRPC escuchando en :5002
```

#### 3. Ejecutar Cliente
```bash
cd Client
python Client.py
```

## 📁 Estructura del Proyecto

```
Top_TelematicaPro1/
├── NameNode/
│   ├── NameNode.py           # Servidor coordinador
│   ├── name_node.proto       # Definición gRPC
│   └── name_node_pb2*.py     # Archivos generados
├── DataNode/
│   ├── DataNode.py           # Servidor de almacenamiento
│   ├── data_node.proto       # Definición gRPC
│   ├── data_node_pb2*.py     # Archivos generados
│   └── data/                 # Directorio de bloques
│       ├── tmp/              # Archivos temporales
│       └── blocks/           # Bloques finalizados (.blk)
├── Client/
│   ├── Client.py             # Cliente principal
│   ├── utilsClient.py        # Utilidades del cliente
│   ├── generadorArchivo.py   # Generador de archivos de prueba
│   └── Archivo128MBOut/      # Directorio de bloques locales
└── README.md
```

## ⚙️ Configuración

### NameNode (NameNode/NameNode.py)
```python
BLOCK_SIZE = 64 * 1024 * 1024    # 64 MB por bloque
DATANODES = [                    # DataNodes disponibles
    "localhost:5002",
]
```

### DataNode (DataNode/DataNode.py)
```python
ROOT_DIR = Path("data")          # Directorio base
TMP_DIR = ROOT_DIR / "tmp"       # Archivos temporales
BLOCKS_DIR = ROOT_DIR / "blocks" # Bloques finalizados
REQUIRED_TOKEN = None            # Token de autenticación (opcional)
```

### Cliente (Client/Client.py)
```python
CHUNK_SIZE = 1 * 1024 * 1024     # 1 MB por chunk de transferencia
namenode_addr = "localhost:50051" # Dirección del NameNode
```

## 🔄 Flujo de Operación

### Subida de Archivos:

1. **Cliente → NameNode**: Solicita plan de escritura (`PlanFileWrite`)
2. **NameNode → Cliente**: Devuelve plan con asignaciones de bloques
3. **Cliente**: Divide archivo en bloques locales usando `utilsClient.py`
4. **Cliente → DataNode**: Sube cada bloque usando streaming gRPC
5. **DataNode**: Guarda bloques como archivos `.blk`

### Mensajes de Confirmación:

El DataNode muestra progreso detallado:
```
[DataNode] ✅ Iniciado recepción del bloque 00000000-12345...
[DataNode] 📥 Recibido 10 MB del bloque 00000000-12345...
[DataNode] 💾 BLOQUE GUARDADO: 00000000-12345... (67108864 bytes) → data/blocks/00000000-12345....blk
[DataNode] ✅ CONFIRMACIÓN: Bloque 00000000-12345... procesado exitosamente
```

## 🐧 Compatibilidad Linux

El código es **completamente multiplataforma** gracias a:

- **`pathlib.Path`**: Maneja automáticamente diferencias de rutas (posición relativa (/filePathAfterProgram/fileName) vs total (C:/filePath/fileName))
- **Librerías estándar**: `grpc`, `hashlib`, `socket` funcionan idénticamente
- **Operaciones atómicas**: `os.replace()` es multiplataforma

### Ejecución en Linux:

```bash
# Instalar dependencias
pip3 install grpcio grpcio-tools

# Ejecutar (usar python3 si es necesario)
python3 NameNode.py
python3 DataNode.py  
python3 Client.py
```

## 🔧 Puertos Utilizados

| Servicio | Puerto | Descripción |
|----------|--------|-------------|
| NameNode | 50051  | Coordinación y metadatos |
| DataNode | 5002   | Almacenamiento de bloques |

> **Nota**: Los puertos > 1024 no requieren privilegios especiales en Linux.

## 📊 Ejemplo de Uso

```python
# El cliente automáticamente:
mf = put_file_with_local_blocks(
    file_path="Archivo128MB.txt",           # Archivo a subir
    remote_path="/users/camilo/Archivo128MB.txt", # Ruta remota
    namenode_addr="localhost:50051",        # NameNode
    auth_token=None                         # Sin autenticación
)
```

## 🛠️ Resolución de Problemas

### Error: "DNS resolution failed for l"
**Causa**: Problema en configuración de DataNodes en NameNode
**Solución**: Verificar que `DATANODES` sea una lista de strings, no caracteres

### Error: "Exception iterating requests"
**Causa**: Problema en generador de requests del cliente
**Solución**: Verificar que `block_path` sea objeto `Path`, no string

### Error: "Connection refused"
**Causa**: Servicios no están corriendo
**Solución**: Verificar orden de inicio (NameNode → DataNode → Cliente)

## 📈 Características

- ✅ **Distribución automática** de bloques
- ✅ **Streaming gRPC** para transferencias eficientes  
- ✅ **Verificación de integridad** con SHA256
- ✅ **Operaciones atómicas** para consistencia
- ✅ **Multiplataforma** (Windows/Linux)
- ✅ **Escalable** (múltiples DataNodes)
- ✅ **Logging detallado** para debugging

## 🔮 Próximas Funcionalidades

- [ ] **Descarga de archivos** (`DownloadBlock`)
- [ ] **Replicación** de bloques entre DataNodes
- [ ] **Tolerancia a fallos** y recuperación
- [ ] **Balanceador de carga** automático
- [ ] **Interfaz web** para administración
