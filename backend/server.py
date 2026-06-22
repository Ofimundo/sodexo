from flask import Flask, jsonify, request, send_from_directory, Response
from flask_cors import CORS
import os
import threading
import json
import traceback
import shutil
import re
from datetime import datetime as dt

# Importar app_ocr (el archivo que modificamos)
import app_ocr

backend_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(backend_dir)
frontend_dist = os.path.join(project_root, "frontend", "dist")

app = Flask(__name__, static_folder=frontend_dist, static_url_path='')
CORS(app)

@app.route('/')
def serve_index():
    if os.path.exists(os.path.join(app.static_folder, 'index.html')):
        return send_from_directory(app.static_folder, 'index.html')
    return "Frontend no compilado. Ejecute 'npm run build' en la carpeta frontend.", 404

# ===== CONSTANTES =====
ERRORS_DIR = os.path.join(project_root, "errores")
is_processing_active = False

# Extensiones soportadas para imágenes
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.webp', '.gif')
SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS + ('.pdf',)

# ===== FUNCIONES DE RUTAS =====

def normalizar_ruta(ruta):
    """Normaliza cualquier tipo de ruta"""
    if not ruta:
        return ruta
    
    ruta = ruta.strip()
    ruta = ruta.replace('\\', '/')
    
    if ruta.startswith('~'):
        ruta = os.path.expanduser(ruta)
    
    if not os.path.isabs(ruta):
        ruta = os.path.abspath(ruta)
    
    return os.path.normpath(ruta)

def validar_y_crear_ruta(ruta):
    """Valida y crea la ruta si es necesario"""
    try:
        ruta_normalizada = normalizar_ruta(ruta)
        os.makedirs(ruta_normalizada, exist_ok=True)
        return ruta_normalizada
    except Exception as e:
        app_ocr.registro_log("ruta", f"Error validando ruta {ruta}: {str(e)}")
        return ruta

def obtener_ruta_errores():
    """Obtiene la ruta de errores"""
    ruta = os.environ.get('DOCS_ERRORS_PATH', '')
    if ruta:
        return ruta
    return os.path.join(project_root, "errores")

def obtener_error_del_log(filename):
    """Extrae el error específico del archivo desde los logs"""
    try:
        log_file = os.path.join(app_ocr.RUTA_LOG, "ejecucion_log.txt")
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                logs = f.readlines()
                for line in reversed(logs):
                    if filename in line and ('error' in line.lower() or 'fallo' in line.lower()):
                        if 'Error:' in line:
                            return line.split('Error:')[-1].strip()[:150]
                        elif 'error' in line.lower():
                            return line.strip()[:150]
        return "Error en procesamiento - Revise los logs"
    except:
        return "Error desconocido"

# ===== ENDPOINTS =====

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Obtener estadísticas del sistema"""
    try:
        pendientes = 0
        ruta_pendientes = normalizar_ruta(app_ocr.RUTA_PENDIENTES)
        if os.path.exists(ruta_pendientes):
            pendientes = len([f for f in os.listdir(ruta_pendientes) 
                            if f.lower().endswith(SUPPORTED_EXTENSIONS)])
        
        procesados = 0
        ruta_procesados = normalizar_ruta(app_ocr.RUTA_PROCESADOS)
        if os.path.exists(ruta_procesados):
            procesados = len([f for f in os.listdir(ruta_procesados) 
                            if f.lower().endswith('.pdf')])
        
        erroneos = 0
        ruta_errores = obtener_ruta_errores()
        if os.path.exists(ruta_errores):
            erroneos = len([f for f in os.listdir(ruta_errores) 
                           if f.lower().endswith(('.pdf', '.jpg', '.jpeg', '.png'))])
        
        activo = False
        intervalo = app_ocr.INTERVALO_MINUTOS if hasattr(app_ocr, 'INTERVALO_MINUTOS') else 5
        
        return jsonify({
            'pendientes': pendientes,
            'procesados': procesados,
            'erroneos': erroneos,
            'activo': activo,
            'intervalo': intervalo
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/pending', methods=['GET'])
def get_pending():
    """Obtener lista de documentos pendientes"""
    try:
        files = []
        ruta_pendientes = normalizar_ruta(app_ocr.RUTA_PENDIENTES)
        if os.path.exists(ruta_pendientes):
            for f in os.listdir(ruta_pendientes):
                if f.lower().endswith(SUPPORTED_EXTENSIONS):
                    path = os.path.join(ruta_pendientes, f)
                    try:
                        stats = os.stat(path)
                        mtime = os.path.getmtime(path)
                        fecha_str = dt.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
                        files.append({
                            'nombre': f,
                            'tamaño': f"{stats.st_size / 1024:.2f} KB",
                            'fecha': fecha_str
                        })
                    except Exception:
                        files.append({
                            'nombre': f,
                            'tamaño': "Error",
                            'fecha': "Sin fecha"
                        })
        return jsonify(files)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/processed', methods=['GET'])
def get_processed():
    """Obtener lista de documentos procesados"""
    try:
        docs = []
        ruta_procesados = normalizar_ruta(app_ocr.RUTA_PROCESADOS)
        
        if os.path.exists(ruta_procesados):
            for archivo in os.listdir(ruta_procesados):
                if archivo.lower().endswith('.pdf'):
                    pdf_path = os.path.join(ruta_procesados, archivo)
                    try:
                        stat = os.stat(pdf_path)
                        docs.append({
                            'nombre': archivo,
                            'tamaño': f"{stat.st_size / 1024:.2f} KB",
                            'fecha': dt.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                            'formato': 'PDF'
                        })
                    except Exception:
                        docs.append({
                            'nombre': archivo,
                            'tamaño': "Desconocido",
                            'fecha': "Sin fecha",
                            'formato': 'PDF'
                        })
        
        return jsonify(docs)
        
    except Exception as e:
        print(f"[ERROR] Error en get_processed: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/errors', methods=['GET'])
def get_errors():
    """Obtener lista de documentos con error"""
    try:
        error_files = []
        ruta_errores = obtener_ruta_errores()
        
        if os.path.exists(ruta_errores):
            for file in os.listdir(ruta_errores):
                file_path = os.path.join(ruta_errores, file)
                try:
                    stat = os.stat(file_path)
                    error_msg = obtener_error_del_log(file)
                    
                    error_files.append({
                        'nombre': file,
                        'error': error_msg,
                        'fecha': dt.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                        'tamaño': f"{stat.st_size / 1024:.2f} KB"
                    })
                except Exception:
                    error_files.append({
                        'nombre': file,
                        'error': "Error al leer archivo",
                        'fecha': "Sin fecha",
                        'tamaño': "Desconocido"
                    })
        
        return jsonify(error_files)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Subir archivos (imagen o PDF)"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No se envió archivo'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No se seleccionó archivo'}), 400
        
        filename = file.filename
        ext = os.path.splitext(filename)[1].lower()
        ruta_pendientes = normalizar_ruta(app_ocr.RUTA_PENDIENTES)
        
        if ext in IMAGE_EXTENSIONS or ext == '.pdf':
            filepath = os.path.join(ruta_pendientes, filename)
            file.save(filepath)
            app_ocr.registro_log("upload", f"Archivo subido: {filename}")
            return jsonify({'success': True, 'message': f'Archivo {filename} subido exitosamente'})
        else:
            return jsonify({
                'success': False,
                'message': f'Formato no soportado: {ext}. Use imágenes (JPG, PNG, GIF, BMP, TIFF, WEBP) o PDF.'
            }), 400
            
    except Exception as e:
        app_ocr.registro_log("upload_error", f"Error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/upload-images', methods=['POST'])
def upload_images():
    """Subir múltiples imágenes"""
    try:
        if 'files' not in request.files:
            return jsonify({'error': 'No se enviaron archivos'}), 400
        
        files = request.files.getlist('files')
        if not files or all(f.filename == '' for f in files):
            return jsonify({'error': 'No se seleccionaron archivos'}), 400
        
        uploaded = 0
        errors = []
        ruta_pendientes = normalizar_ruta(app_ocr.RUTA_PENDIENTES)
        
        for file in files:
            if file.filename == '':
                continue
            
            filename = file.filename
            ext = os.path.splitext(filename)[1].lower()
            
            if ext in IMAGE_EXTENSIONS or ext == '.pdf':
                try:
                    filepath = os.path.join(ruta_pendientes, filename)
                    file.save(filepath)
                    uploaded += 1
                    app_ocr.registro_log("upload", f"Archivo subido: {filename}")
                except Exception as e:
                    errors.append(f"{filename}: {str(e)}")
            else:
                errors.append(f"{filename}: Formato no soportado")
        
        if uploaded > 0:
            return jsonify({
                'success': True,
                'message': f'Se subieron {uploaded} archivos correctamente',
                'uploaded': uploaded,
                'errors': errors if errors else None
            })
        else:
            return jsonify({
                'success': False,
                'message': 'No se pudo subir ningún archivo',
                'errors': errors
            }), 400
            
    except Exception as e:
        app_ocr.registro_log("upload_error", f"Error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/convert-images', methods=['POST'])
def convert_images():
    """Convertir imágenes a PDF - llama a la función de app_ocr"""
    try:
        # Usar la función de app_ocr
        resultado = app_ocr.ejecutar_conversion()
        
        if resultado:
            converted, errors = resultado
            return jsonify({
                'success': True,
                'message': f'Se procesaron {converted} archivos correctamente',
                'converted': converted,
                'errors': errors if errors > 0 else None
            })
        else:
            return jsonify({
                'success': False,
                'message': 'No se procesaron archivos'
            })
            
    except Exception as e:
        app_ocr.registro_log("convert_error", f"Error general: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/process', methods=['POST'])
def trigger_process():
    """Iniciar proceso de conversión en segundo plano"""
    try:
        # Ejecutar conversión en hilo separado
        def run_conversion():
            try:
                app_ocr.ejecutar_conversion()
            except Exception as e:
                app_ocr.registro_log("process_error", f"Error: {str(e)}")
        
        thread = threading.Thread(target=run_conversion)
        thread.daemon = True
        thread.start()
        
        return jsonify({'success': True, 'message': 'Conversión iniciada en segundo plano'})
        
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/retry-error/<path:filename>', methods=['POST'])
def retry_error_document(filename):
    """Reintentar procesar un documento que tuvo error"""
    try:
        ruta_errores = obtener_ruta_errores()
        error_file_path = os.path.join(ruta_errores, filename)
        ruta_pendientes = normalizar_ruta(app_ocr.RUTA_PENDIENTES)
        pending_file_path = os.path.join(ruta_pendientes, filename)
        
        if os.path.exists(error_file_path):
            shutil.move(error_file_path, pending_file_path)
            app_ocr.registro_log("retry_error", f"Documento {filename} movido de errores a pendientes")
            return jsonify({'success': True, 'message': 'Documento enviado a procesar nuevamente'})
        else:
            return jsonify({'error': 'Archivo no encontrado'}), 404
            
    except Exception as e:
        app_ocr.registro_log("retry_error", f"Error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/retry-all-errors', methods=['POST'])
def retry_all_errors():
    """Reintentar todos los documentos con error"""
    try:
        moved_count = 0
        ruta_errores = obtener_ruta_errores()
        ruta_pendientes = normalizar_ruta(app_ocr.RUTA_PENDIENTES)
        
        if os.path.exists(ruta_errores):
            for filename in os.listdir(ruta_errores):
                error_path = os.path.join(ruta_errores, filename)
                pending_path = os.path.join(ruta_pendientes, filename)
                shutil.move(error_path, pending_path)
                moved_count += 1
                app_ocr.registro_log("retry_all_errors", f"Documento {filename} movido a pendientes")
        
        return jsonify({
            'success': True, 
            'message': f'Se movieron {moved_count} documentos a la carpeta de pendientes'
        })
    except Exception as e:
        app_ocr.registro_log("retry_all_errors", f"Error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/delete-error/<path:filename>', methods=['DELETE'])
def delete_error_document(filename):
    """Eliminar un documento de la carpeta de errores"""
    try:
        ruta_errores = obtener_ruta_errores()
        file_path = os.path.join(ruta_errores, filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            app_ocr.registro_log("delete_error", f"Documento {filename} eliminado de errores")
            return jsonify({'success': True, 'message': 'Documento eliminado'})
        else:
            return jsonify({'error': 'Archivo no encontrado'}), 404
    except Exception as e:
        app_ocr.registro_log("delete_error", f"Error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/download/<nombre>', methods=['GET'])
def download_pdf(nombre):
    """Descargar PDF generado"""
    try:
        ruta_procesados = normalizar_ruta(app_ocr.RUTA_PROCESADOS)
        
        if os.path.exists(ruta_procesados):
            if nombre in os.listdir(ruta_procesados):
                return send_from_directory(ruta_procesados, nombre, as_attachment=True)
        
        return jsonify({'error': 'PDF no encontrado'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/open/<nombre>', methods=['POST'])
def open_folder(nombre):
    """Abrir carpeta del documento procesado"""
    try:
        ruta_procesados = normalizar_ruta(app_ocr.RUTA_PROCESADOS)
        
        if os.path.exists(ruta_procesados):
            if nombre in os.listdir(ruta_procesados):
                os.startfile(ruta_procesados)
                return jsonify({'success': True, 'carpeta': ruta_procesados})
        
        return jsonify({'error': 'Carpeta no encontrada'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stop', methods=['POST'])
def stop_process():
    """Detener proceso activo"""
    try:
        app_ocr.solicitar_detencion()
        return jsonify({'success': True, 'message': 'Solicitud de detención enviada'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/logs', methods=['GET'])
def get_logs():
    """Obtener logs del sistema"""
    try:
        log_file = os.path.join(app_ocr.RUTA_LOG, "ejecucion_log.txt")
        if not os.path.exists(log_file):
            return jsonify({'logs': []})
            
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        return jsonify({'logs': [line.strip() for line in lines[-100:]]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/logs/clear', methods=['POST'])
def clear_logs():
    """Limpiar archivo de logs"""
    try:
        log_file = os.path.join(app_ocr.RUTA_LOG, "ejecucion_log.txt")
        timestamp = dt.now().strftime('%Y-%m-%d %H:%M:%S')
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(f"--- Log limpiado por el usuario el {timestamp} ---\n")
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/logs/download', methods=['GET'])
def download_logs():
    """Descargar archivo de logs"""
    try:
        log_file = os.path.join(app_ocr.RUTA_LOG, "ejecucion_log.txt")
        if not os.path.exists(log_file):
            return jsonify({'error': 'Log file not found'}), 404
        with open(log_file, 'r', encoding='utf-8') as f:
            content = f.read()
        filename = f"logs_{dt.now().strftime('%Y%m%d_%H%M%S')}.txt"
        return Response(
            content,
            mimetype='text/plain',
            headers={
                'Content-Disposition': f'attachment; filename={filename}',
                'Access-Control-Allow-Origin': '*'
            }
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ===== CONFIGURACIÓN =====
CONFIG_FILE = os.path.join(project_root, "config_web.json")

def load_config_from_file():
    """Cargar configuración desde archivo"""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if 'ruta_pendientes' in data:
                    app_ocr.RUTA_PENDIENTES = normalizar_ruta(data['ruta_pendientes'])
                    validar_y_crear_ruta(app_ocr.RUTA_PENDIENTES)
                if 'ruta_procesados' in data:
                    app_ocr.RUTA_PROCESADOS = normalizar_ruta(data['ruta_procesados'])
                    validar_y_crear_ruta(app_ocr.RUTA_PROCESADOS)
                if 'intervalo' in data:
                    app_ocr.INTERVALO_MINUTOS = int(data['intervalo'])
                return True
    except Exception as e:
        print(f"Error loading config file: {e}")
    return False

def save_config_to_file():
    """Guardar configuración en archivo"""
    try:
        data = {
            'ruta_pendientes': app_ocr.RUTA_PENDIENTES,
            'ruta_procesados': app_ocr.RUTA_PROCESADOS,
            'intervalo': app_ocr.INTERVALO_MINUTOS
        }
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving config file: {e}")
    return False

@app.route('/api/config', methods=['GET'])
def get_config():
    """Obtener configuración actual"""
    return jsonify({
        'ruta_pendientes': app_ocr.RUTA_PENDIENTES,
        'ruta_procesados': app_ocr.RUTA_PROCESADOS,
        'intervalo': app_ocr.INTERVALO_MINUTOS if hasattr(app_ocr, 'INTERVALO_MINUTOS') else 5,
        'persistente': os.path.exists(CONFIG_FILE)
    })

@app.route('/api/config', methods=['POST'])
def update_config():
    """Actualizar configuración"""
    try:
        data = request.json
        
        if 'ruta_pendientes' in data:
            ruta = normalizar_ruta(data['ruta_pendientes'])
            app_ocr.RUTA_PENDIENTES = validar_y_crear_ruta(ruta)
            app_ocr.registro_log("config", f"Ruta pendientes: {app_ocr.RUTA_PENDIENTES}")
            
        if 'ruta_procesados' in data:
            ruta = normalizar_ruta(data['ruta_procesados'])
            app_ocr.RUTA_PROCESADOS = validar_y_crear_ruta(ruta)
            app_ocr.registro_log("config", f"Ruta procesados: {app_ocr.RUTA_PROCESADOS}")
            
        if 'intervalo' in data:
            app_ocr.INTERVALO_MINUTOS = int(data['intervalo'])
            app_ocr.registro_log("config", f"Intervalo: {app_ocr.INTERVALO_MINUTOS} minutos")
        
        if data.get('guardar_permanente'):
            save_config_to_file()
        elif os.path.exists(CONFIG_FILE) and data.get('borrar_permanente'):
            os.remove(CONFIG_FILE)
            
        return jsonify({'success': True, 'message': 'Configuración actualizada'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/validate-path', methods=['POST'])
def validate_path():
    """Validar si una ruta es accesible"""
    try:
        data = request.json
        ruta = data.get('path', '')
        
        if not ruta:
            return jsonify({'valid': False, 'message': 'Ruta vacía'})
        
        ruta_normalizada = normalizar_ruta(ruta)
        
        try:
            os.makedirs(ruta_normalizada, exist_ok=True)
            test_file = os.path.join(ruta_normalizada, '.test_write')
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
            
            return jsonify({
                'valid': True,
                'message': 'Ruta válida y accesible',
                'normalized_path': ruta_normalizada
            })
        except Exception as e:
            return jsonify({
                'valid': False,
                'message': f'No se puede acceder a la ruta: {str(e)}'
            })
            
    except Exception as e:
        return jsonify({'valid': False, 'message': str(e)}), 500

# ===== SCHEDULER =====
def start_scheduler():
    """Iniciar el scheduler para procesamiento automático"""
    try:
        import schedule
        import time
        
        def run_schedule():
            while True:
                schedule.run_pending()
                time.sleep(1)
        
        def scheduled_process():
            app_ocr.registro_log("scheduler", f"Ejecución automática programada")
            try:
                app_ocr.ejecutar_conversion()
            except Exception as e:
                app_ocr.registro_log("scheduler", f"Error: {str(e)}")
        
        intervalo = app_ocr.INTERVALO_MINUTOS if hasattr(app_ocr, 'INTERVALO_MINUTOS') else 5
        schedule.every(intervalo).minutes.do(scheduled_process)
        app_ocr.registro_log("scheduler", f"Scheduler iniciado cada {intervalo} minutos")
        
        thread = threading.Thread(target=run_schedule)
        thread.daemon = True
        thread.start()
    except Exception as e:
        print(f"Error iniciando scheduler: {e}")

# ===== INICIO =====
if __name__ == '__main__':
    # Crear directorios necesarios
    os.makedirs(app_ocr.RUTA_PENDIENTES, exist_ok=True)
    os.makedirs(app_ocr.RUTA_PROCESADOS, exist_ok=True)
    os.makedirs(obtener_ruta_errores(), exist_ok=True)
    os.makedirs(app_ocr.RUTA_LOG, exist_ok=True)
    
    # Cargar configuración guardada
    load_config_from_file()
    
    # Iniciar scheduler
    start_scheduler()
    
    print("=" * 60)
    print("🔄 CONVERSOR DE IMÁGENES A PDF - BACKEND")
    print("=" * 60)
    print(f"🌐 Servidor: http://localhost:5000")
    print(f"📁 Pendientes: {app_ocr.RUTA_PENDIENTES}")
    print(f"📁 Procesados: {app_ocr.RUTA_PROCESADOS}")
    print(f"📁 Errores:    {obtener_ruta_errores()}")
    print(f"⏱️ Intervalo:  {app_ocr.INTERVALO_MINUTOS} minutos")
    print("=" * 60)
    print("📌 Formatos soportados:")
    print("   🖼️ Imágenes: JPG, PNG, GIF, BMP, TIFF, WEBP")
    print("   📄 PDFs (se mueven directamente)")
    print("=" * 60)
    print("🔧 SIN OCR - Solo conversión de imágenes a PDF")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)