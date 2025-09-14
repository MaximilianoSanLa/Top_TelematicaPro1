import uuid       # Librería para generar identificadores únicos (block_id)
import json       # Para guardar/leer el manifest en formato JSON
import hashlib    # Para calcular hashes SHA-256 de los bloques
from pathlib import Path  # Manejo de rutas de archivos de forma más clara
import shutil     # Para eliminar directorios y archivos
import os         # Para operaciones del sistema de archivos


def dividir_bloque(fileName: str, block_size: int = None) -> str:
    """
    Divide un archivo en bloques del tamaño especificado y crea automáticamente
    una carpeta de salida con el nombre <archivo>_out.
    Devuelve la ruta al manifest.json.
    Args:
        fileName: Ruta del archivo a dividir
        block_size: Tamaño de bloque en bytes. Si es None, usa 64MB por defecto.
    """
    path = Path(fileName).resolve()
    out = path.parent / f"{path.stem}Out"
    blocks = out / "blocks"
    fileTemp = out / "temp"
    blocks.mkdir(parents=True, exist_ok=True)
    fileTemp.mkdir(parents=True, exist_ok=True)
    fileSize = path.stat().st_size
    BLOCK_SIZE = block_size
    print(f"Name: {path.name}, Size: {fileSize/1024/1024:.2f} MB")

    manifest = {
        "name": path.name,
        "size": fileSize,
        "block_size": BLOCK_SIZE,
        "blocks": []
    }

    totalChunks = 0
    block_index = 0
    ArchivoFaltante = fileSize
    with open(path, "rb") as file:
        while ArchivoFaltante > 0:
            SizeBloque = min(ArchivoFaltante, BLOCK_SIZE) #Tamaño del bloque puede que sea menor al block_size
            bloque_id = str(uuid.uuid4()) #ID del bloque
            chunkTempPath = fileTemp / f"{block_index:08d}-{bloque_id}.tmp" #Ruta del bloque temporal
            hasher = hashlib.sha256() #Hasher para el bloque
            SizeBloqueActual = 0 #Tamaño actual del bloque
            with open(chunkTempPath, "wb") as chunkTemp:
               while SizeBloqueActual < SizeBloque:
                  ChunkSize = 1 * 1024 * 1024
                  data = file.read(min(ChunkSize, SizeBloque - SizeBloqueActual))#Escriba chunks hasta ya no haya mas datos
                  if not data:
                     break
                  chunkTemp.write(data)
                  hasher.update(data)
                  SizeBloqueActual += len(data)
                  totalChunks += 1
                  print(f"Bloque lleva {SizeBloqueActual/1024/1024:.2f} MB de {SizeBloque/1024/1024:.2f} MB con total de {totalChunks} chunks")
            
            # Mover el bloque temporal a la carpeta final
            finalBlockPath = blocks / f"{block_index:08d}-{bloque_id}.bin"
            shutil.move(chunkTempPath, finalBlockPath)
            
            # Agregar información del bloque al manifest
            manifest["blocks"].append({
                "index": block_index,
                "id": bloque_id,
                "size": SizeBloqueActual,
                "hash": hasher.hexdigest(),
                "path": str(finalBlockPath)
            })
            
            ArchivoFaltante -= SizeBloqueActual
            block_index += 1
            print(f"Bloque {block_index-1} completado: {SizeBloqueActual/1024/1024:.2f} MB")
    
    # Guardar el manifest
    manifestPath = out / "manifest.json"
    with open(manifestPath, "w") as f:
        json.dump(manifest, f, indent=2)
    
    print(f" División completada. {block_index} bloques creados.")
    print(f" Manifest guardado en: {manifestPath}")
    
    return str(manifestPath)










    
    




