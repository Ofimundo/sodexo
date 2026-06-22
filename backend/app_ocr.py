import os
import shutil
import time
import threading
from datetime import datetime
from PIL import Image as PILImage
import re
import subprocess

# ==================== CONFIGURACIÓN ====================
backend_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(backend_dir)

# ===== AGREGAR ESTA LÍNEA =====
INTERVALO_MINUTOS = 5  # Intervalo por defecto para el scheduler

# Rutas - CON SOPORTE PARA RUTAS DE RED
RUTA_PENDIENTES = os.environ.get('DOCS_PENDING_PATH', os.path.join(project_root, "doc_pendientes"))
RUTA_PROCESADOS = os.environ.get('DOCS_PROCESSED_PATH', os.path.join(project_root, "doc_procesados"))
RUTA_ERRORES = os.environ.get('DOCS_ERRORS_PATH', os.path.join(project_root, "errores"))
RUTA_LOG = os.path.join(project_root, "log")

# Extensiones de imagen soportadas
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.webp', '.gif')

# Configuración de calidad PDF
CALIDAD_PDF = {
    'dpi': 300,  # Resolución en DPI (mayor = mejor calidad)
    'calidad_jpeg': 95,  # Calidad JPEG (1-100, mayor = mejor)
    'optimizar': True,  # Optimizar tamaño
    'color': 'RGB'  # Modo de color
}

# Variable global para control
STOP_REQUESTED = False
log_lock = threading.Lock()

# ==================== FUNCIONES DE LOGGING ====================

def registro_log(proceso: str, dato: str) -> None:
    """Registra eventos en el log"""
    try:
        with log_lock:
            os.makedirs(RUTA_LOG, exist_ok=True)
            with open(os.path.join(RUTA_LOG, "ejecucion_log.txt"), 'a', encoding='utf-8') as file:
                fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                file.write(f"{fecha_hora} - {proceso} - {dato}\n")
            print(f"{fecha_hora} - {proceso} - {dato}")
    except Exception as e:
        print(f"Error al escribir log: {e}")

# ==================== FUNCIONES DE CONVERSIÓN CON CALIDAD MEJORADA ====================

def convertir_imagen_a_pdf_calidad(ruta_imagen: str, ruta_destino: str) -> bool:
    """Convierte una imagen a PDF con alta calidad"""
    try:
        # Abrir imagen
        img = PILImage.open(ruta_imagen)
        
        # Registrar tamaño original para log
        ancho_original, alto_original = img.size
        modo_original = img.mode
        
        registro_log("convert", f"  📐 Imagen: {ancho_original}x{alto_original}px, Modo: {modo_original}")
        
        # Mejorar calidad: redimensionar si es muy pequeña
        dpi_objetivo = CALIDAD_PDF['dpi']
        
        # Si la imagen es muy pequeña, aumentar tamaño (para mejorar calidad)
        if ancho_original < 800 or alto_original < 600:
            factor = max(800 / ancho_original, 600 / alto_original)
            nuevo_ancho = int(ancho_original * factor)
            nuevo_alto = int(alto_original * factor)
            img = img.resize((nuevo_ancho, nuevo_alto), PILImage.Resampling.LANCZOS)
            registro_log("convert", f"  🔍 Imagen redimensionada: {nuevo_ancho}x{nuevo_alto}px")
        
        # Convertir a RGB si es necesario
        if img.mode in ('RGBA', 'P', 'LA', 'PA'):
            registro_log("convert", f"  🎨 Convirtiendo de {img.mode} a RGB")
            
            # Crear fondo blanco
            background = PILImage.new('RGB', img.size, (255, 255, 255))
            
            if img.mode == 'P':
                img = img.convert('RGBA')
            
            # Pegar imagen con transparencia
            if 'A' in img.mode:
                background.paste(img, mask=img.split()[-1])
            else:
                background.paste(img)
            
            img = background
            
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Aplicar mejora de nitidez (opcional)
        try:
            from PIL import ImageEnhance
            enhancer = ImageEnhance.Sharpness(img)
            img = enhancer.enhance(1.2)  # Aumentar nitidez 20%
        except:
            pass  # Si no funciona, continuar
        
        # Guardar como PDF con alta calidad - DIRECTAMENTE en la carpeta procesados
        img.save(
            ruta_destino, 
            'PDF',
            resolution=dpi_objetivo,
            quality=CALIDAD_PDF['calidad_jpeg'],
            optimize=CALIDAD_PDF['optimizar'],
            compress_level=1  # Menor compresión = mejor calidad
        )
        
        # Verificar tamaño del archivo generado
        if os.path.exists(ruta_destino):
            size_kb = os.path.getsize(ruta_destino) / 1024
            registro_log("convert", f"  📄 PDF generado: {size_kb:.2f} KB, DPI: {dpi_objetivo}")
        
        return True
        
    except Exception as e:
        registro_log("convert_error", f"❌ Error convirtiendo {ruta_imagen}: {e}")
        return False

def procesar_imagenes_pendientes():
    """Procesa todas las imágenes en la carpeta de pendientes con alta calidad"""
    if not os.path.exists(RUTA_PENDIENTES):
        registro_log("procesar", f"❌ La ruta no existe: {RUTA_PENDIENTES}")
        return
    
    # Obtener todas las imágenes
    archivos = [f for f in os.listdir(RUTA_PENDIENTES) 
                if f.lower().endswith(IMAGE_EXTENSIONS)]
    
    if len(archivos) == 0:
        registro_log("procesar", "ℹ️ No hay imágenes para procesar")
        return
    
    registro_log("procesar", f"📊 Total de imágenes: {len(archivos)}")
    registro_log("procesar", f"⚙️ Calidad: {CALIDAD_PDF['dpi']} DPI, JPEG {CALIDAD_PDF['calidad_jpeg']}%")
    
    # Crear carpetas si no existen
    os.makedirs(RUTA_PROCESADOS, exist_ok=True)
    os.makedirs(RUTA_ERRORES, exist_ok=True)
    
    convertidos = 0
    errores = 0
    
    for idx, archivo in enumerate(archivos, 1):
        if STOP_REQUESTED:
            registro_log("procesar", "🛑 Procesamiento detenido por solicitud")
            break
        
        ruta_imagen = os.path.join(RUTA_PENDIENTES, archivo)
        nombre_base = os.path.splitext(archivo)[0]
        nombre_pdf = f"{nombre_base}.pdf"
        # GUARDAR DIRECTAMENTE EN RUTA_PROCESADOS, sin subcarpetas
        ruta_pdf = os.path.join(RUTA_PROCESADOS, nombre_pdf)
        
        registro_log("procesar", f"🔄 [{idx}/{len(archivos)}] Procesando: {archivo}")
        
        try:
            # Si ya existe, agregar timestamp
            if os.path.exists(ruta_pdf):
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                nombre_pdf = f"{nombre_base}_{timestamp}.pdf"
                ruta_pdf = os.path.join(RUTA_PROCESADOS, nombre_pdf)
                registro_log("procesar", f"  📝 PDF ya existe, guardando como: {nombre_pdf}")
            
            # Convertir con alta calidad
            if convertir_imagen_a_pdf_calidad(ruta_imagen, ruta_pdf):
                # Eliminar la imagen original
                os.remove(ruta_imagen)
                convertidos += 1
                registro_log("procesar", f"✅ Convertido: {archivo} -> {nombre_pdf}")
            else:
                # Mover a errores
                ruta_error = os.path.join(RUTA_ERRORES, archivo)
                shutil.move(ruta_imagen, ruta_error)
                errores += 1
                registro_log("procesar", f"❌ Error con {archivo} - movido a errores")
                
        except Exception as e:
            registro_log("procesar", f"❌ Error con {archivo}: {e}")
            try:
                ruta_error = os.path.join(RUTA_ERRORES, archivo)
                shutil.move(ruta_imagen, ruta_error)
                errores += 1
            except:
                pass
    
    registro_log("procesar", f"✅ COMPLETADO: {convertidos} convertidos, {errores} errores")
    return convertidos, errores

def procesar_imagen_individual(ruta_imagen: str) -> bool:
    """Procesa una imagen individual con alta calidad (para subida manual)"""
    try:
        if not os.path.exists(ruta_imagen):
            return False
        
        nombre_base = os.path.splitext(os.path.basename(ruta_imagen))[0]
        nombre_pdf = f"{nombre_base}.pdf"
        # GUARDAR DIRECTAMENTE EN RUTA_PROCESADOS
        ruta_pdf = os.path.join(RUTA_PROCESADOS, nombre_pdf)
        
        # Si ya existe, agregar timestamp
        if os.path.exists(ruta_pdf):
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            nombre_pdf = f"{nombre_base}_{timestamp}.pdf"
            ruta_pdf = os.path.join(RUTA_PROCESADOS, nombre_pdf)
        
        return convertir_imagen_a_pdf_calidad(ruta_imagen, ruta_pdf)
        
    except Exception as e:
        registro_log("convert_error", f"Error procesando imagen: {e}")
        return False

# ==================== FUNCIONES DE CONTROL ====================

def solicitar_detencion():
    """Solicita la detención del proceso"""
    global STOP_REQUESTED
    STOP_REQUESTED = True
    registro_log("sistema", "🛑 Solicitud de detención recibida")

def hay_solicitud_detencion():
    """Verifica si hay una solicitud de detención"""
    global STOP_REQUESTED
    return STOP_REQUESTED

def resetear_detencion():
    """Resetea la solicitud de detención"""
    global STOP_REQUESTED
    STOP_REQUESTED = False

def ejecutar_conversion():
    """Ejecuta la conversión de imágenes"""
    resetear_detencion()
    return procesar_imagenes_pendientes()

# ==================== FUNCIONES PARA RUTAS DE RED ====================

def normalizar_ruta_red(ruta: str) -> str:
    """Normaliza cualquier tipo de ruta"""
    if not ruta:
        return ruta
    
    ruta = ruta.strip()
    ruta = ruta.replace('\\', '/')
    
    if not os.path.isabs(ruta):
        ruta = os.path.abspath(ruta)
    
    return os.path.normpath(ruta)

def actualizar_rutas(config_data: dict):
    """Actualiza las rutas desde la configuración"""
    global RUTA_PENDIENTES, RUTA_PROCESADOS, RUTA_ERRORES
    
    try:
        if 'ruta_pendientes' in config_data and config_data['ruta_pendientes']:
            RUTA_PENDIENTES = normalizar_ruta_red(config_data['ruta_pendientes'])
            os.makedirs(RUTA_PENDIENTES, exist_ok=True)
            
        if 'ruta_procesados' in config_data and config_data['ruta_procesados']:
            RUTA_PROCESADOS = normalizar_ruta_red(config_data['ruta_procesados'])
            os.makedirs(RUTA_PROCESADOS, exist_ok=True)
            
        if 'ruta_errores' in config_data and config_data['ruta_errores']:
            RUTA_ERRORES = normalizar_ruta_red(config_data['ruta_errores'])
            os.makedirs(RUTA_ERRORES, exist_ok=True)
            
        return True
    except Exception as e:
        registro_log("config", f"Error actualizando rutas: {e}")
        return False

# ==================== ESTADÍSTICAS ====================

def obtener_estadisticas():
    """Obtiene estadísticas del sistema"""
    pendientes = 0
    procesados = 0
    errores = 0
    
    if os.path.exists(RUTA_PENDIENTES):
        pendientes = len([f for f in os.listdir(RUTA_PENDIENTES) 
                         if f.lower().endswith(IMAGE_EXTENSIONS)])
    
    if os.path.exists(RUTA_PROCESADOS):
        procesados = len([f for f in os.listdir(RUTA_PROCESADOS) 
                         if f.lower().endswith('.pdf')])
    
    if os.path.exists(RUTA_ERRORES):
        errores = len([f for f in os.listdir(RUTA_ERRORES)])
    
    return {
        'pendientes': pendientes,
        'procesados': procesados,
        'erroneos': errores,
        'activo': False
    }

def contar_imagenes_pendientes():
    """Cuenta las imágenes pendientes"""
    if not os.path.exists(RUTA_PENDIENTES):
        return 0
    return len([f for f in os.listdir(RUTA_PENDIENTES) 
                if f.lower().endswith(IMAGE_EXTENSIONS)])

# ==================== CONFIGURACIÓN DE CALIDAD ====================

def configurar_calidad(dpi: int = 300, calidad_jpeg: int = 95, optimizar: bool = True):
    """Configura la calidad de los PDFs generados"""
    global CALIDAD_PDF
    
    CALIDAD_PDF['dpi'] = dpi
    CALIDAD_PDF['calidad_jpeg'] = calidad_jpeg
    CALIDAD_PDF['optimizar'] = optimizar
    
    registro_log("config", f"⚙️ Calidad configurada: {dpi} DPI, JPEG {calidad_jpeg}%")
    return CALIDAD_PDF

# ==================== MAIN ====================

def inicializar_sistema():
    """Inicializa el sistema"""
    os.makedirs(RUTA_PENDIENTES, exist_ok=True)
    os.makedirs(RUTA_PROCESADOS, exist_ok=True)
    os.makedirs(RUTA_ERRORES, exist_ok=True)
    os.makedirs(RUTA_LOG, exist_ok=True)
    
    registro_log("sistema", "✅ Sistema inicializado correctamente")
    registro_log("sistema", f"⚙️ Calidad PDF: {CALIDAD_PDF['dpi']} DPI")

def main():
    print("=" * 60)
    print("🌟 CONVERSOR DE IMÁGENES A PDF - ALTA CALIDAD 🌟")
    print("=" * 60)
    print(f"📌 Calidad: {CALIDAD_PDF['dpi']} DPI")
    print(f"   JPEG Quality: {CALIDAD_PDF['calidad_jpeg']}%")
    print("   Optimización: Activada")
    print("=" * 60)
    print("   Formatos soportados: JPG, PNG, GIF, BMP, TIFF, WEBP")
    print("=" * 60)
    
    inicializar_sistema()
    
    print(f"\n📁 Pendientes: {RUTA_PENDIENTES}")
    print(f"📁 Procesados: {RUTA_PROCESADOS}  ← TODOS LOS PDFS AQUÍ")
    print(f"📁 Errores:    {RUTA_ERRORES}")
    print("\nℹ️ Para iniciar el servidor web, ejecute 'server.py'")
    print("=" * 60)

if __name__ == "__main__":
    main()