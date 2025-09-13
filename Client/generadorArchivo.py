import os
import time

def generar_archivo_128mb_rapido():
    """Genera un archivo de 128 MB de forma más eficiente"""
    
    # Configuración
    target_size = 128 * 1024 * 1024  # 128 MB en bytes
    archivo_nombre = "Archivo128MB.txt"
    # Asegurar que se cree dentro de la carpeta del cliente (misma carpeta de este script)
    cliente_dir = os.path.dirname(os.path.abspath(__file__))
    archivo_path = os.path.join(cliente_dir, archivo_nombre)
    
    print(f"Generando archivo de {target_size:,} bytes ({target_size / (1024*1024):.0f} MB)...")
    print(f"Archivo: {archivo_path}")
    
    start_time = time.time()
    
    # Crear un patrón más grande para escribir menos veces
    patron = """=== BLOQUE {num:08d} ===
Este es un archivo de prueba de 128 MB para demostrar la lectura en bloques de archivos grandes.
Cada línea contiene información adicional para llenar el archivo hasta el tamaño objetivo.
Esta es la línea {num} de muchas repeticiones.
Contenido adicional para llenar el archivo hasta 128 MB.
Contenido adicional para llenar el archivo hasta 128 MB.
Contenido adicional para llenar el archivo hasta 128 MB.
Contenido adicional para llenar el archivo hasta 128 MB.
Contenido adicional para llenar el archivo hasta 128 MB.

"""
    
    # Calcular cuántas veces necesitamos escribir el patrón
    patron_bytes = patron.encode('utf-8')
    repeticiones = target_size // len(patron_bytes) + 1
    
    print(f"Tamaño del patrón: {len(patron_bytes):,} bytes")
    print(f"Repeticiones necesarias: {repeticiones:,}")
    print("Generando archivo...")
    
    # Crear el archivo
    with open(archivo_path, "w", encoding="utf-8") as file:
        for i in range(repeticiones):
            file.write(patron.format(num=i+1))
            
            # Mostrar progreso cada 5000 bloques
            if (i + 1) % 5000 == 0:
                elapsed = time.time() - start_time
                print(f"Progreso: {i+1:,} bloques completados ({elapsed:.1f}s)")
    
    # Verificar el tamaño final
    file_size = os.path.getsize(archivo_path)
    elapsed_total = time.time() - start_time
    
    print(f"\n✅ Archivo creado exitosamente!")
    print(f"Archivo: {archivo_path}")
    print(f"Tamaño final: {file_size:,} bytes ({file_size / (1024*1024):.2f} MB)")
    print(f"Tiempo de generación: {elapsed_total:.1f} segundos")
    
    if file_size >= target_size:
        print("✅ El archivo tiene al menos 128 MB")
    else:
        print(f"❌ El archivo es más pequeño que 128 MB (falta {target_size - file_size:,} bytes)")
    
    return archivo_path

if __name__ == "__main__":
    generar_archivo_128mb_rapido()

