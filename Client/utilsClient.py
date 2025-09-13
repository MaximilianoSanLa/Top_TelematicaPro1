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

    """name->ArchivoPrueba.txt
       parent->./
       stem->ArchivoPrueba
       suffix->.txt
    """

    path = Path(fileName).resolve()
    out = path.parent / f"{path.stem}Out"
    blocks = out / "blocks"
    fileTemp = out / "temp"
    blocks.mkdir(parents=True, exist_ok=True)
    fileTemp.mkdir(parents=True, exist_ok=True)
    fileSize = path.stat().st_size
    
    # Usar el block_size del plan si se proporciona, sino usar 64MB por defecto
    BLOCK_SIZE = block_size if block_size is not None else 64 * 1024 * 1024
    
    print(f"Name: {path.name}, Size: {fileSize/1024/1024:.2f} MB")
    print(f"BLOCK_SIZE: {BLOCK_SIZE/1024/1024:.2f} MB")
    
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
            SizeBloque = min(ArchivoFaltante, BLOCK_SIZE)
            bloque_id = str(uuid.uuid4())
            chunkTempPath = fileTemp / f"{block_index:08d}-{bloque_id}.tmp"
            hasher = hashlib.sha256()
            SizeBloqueActual = 0
            with open(chunkTempPath, "wb") as chunkTemp:
               while SizeBloqueActual < SizeBloque:
                  ChunkSize = 1 * 1024 * 1024
                  data = file.read(min(ChunkSize, SizeBloque - SizeBloqueActual))
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
    
    print(f"✅ División completada. {block_index} bloques creados.")
    print(f"📁 Manifest guardado en: {manifestPath}")
    
    return str(manifestPath)




def limpiar_archivos_temporales(fileName:str):
    """
    Elimina los archivos temporales generados durante la división de bloques.
    """
    path = Path(fileName).resolve()
    out = path.parent / f"{path.stem}Out"
    temp_dir = out / "temp"
    
    if temp_dir.exists():
        try:
            print(f"🧹 Limpiando archivos temporales en: {temp_dir}")
            shutil.rmtree(temp_dir)
            print("✅ Archivos temporales eliminados exitosamente")
        except Exception as e:
            print(f"❌ Error al eliminar archivos temporales: {e}")
    else:
        print("ℹ️ No se encontraron archivos temporales para limpiar")


def limpiar_todo(fileName:str):
    """
    Elimina toda la carpeta de salida generada por la división de bloques.
    """
    path = Path(fileName).resolve()
    out = path.parent / f"{path.stem}Out"
    
    if out.exists():
        try:
            print(f"🧹 Eliminando toda la carpeta de salida: {out}")
            shutil.rmtree(out)
            print("✅ Carpeta de salida eliminada exitosamente")
        except Exception as e:
            print(f"❌ Error al eliminar carpeta de salida: {e}")
    else:
        print("ℹ️ No se encontró carpeta de salida para eliminar")


def reconstruir_archivo_txt(manifestPath:str, outputPath:str=None):
    """
    Reconstruye el archivo original desde bloques guardados en formato TXT.
    """
    with open(manifestPath, "r") as f:
        manifest = json.load(f)
    
    if outputPath is None:
        outputPath = f"reconstruido_{manifest['name']}"
    
    print(f"🔧 Reconstruyendo archivo: {manifest['name']}")
    print(f"📁 Archivo de salida: {outputPath}")
    
    with open(outputPath, "wb") as output_file:
        for block_info in manifest["blocks"]:
            block_path = Path(block_info["path"])
            print(f"📖 Leyendo bloque {block_info['index']}: {block_path.name}")
            
            with open(block_path, "r", encoding='utf-8') as txt_file:
                lines = txt_file.readlines()
                # Encontrar la línea que contiene los datos Base64
                for line in lines:
                    if not line.startswith("#"):
                        import base64
                        binary_data = base64.b64decode(line.strip())
                        output_file.write(binary_data)
                        break
    
    print(f"✅ Archivo reconstruido exitosamente: {outputPath}")
    return outputPath







    
    




