from flask import Flask, jsonify, request, send_from_directory, Response
from flask_cors import CORS
import os
import threading
import json
import traceback
import shutil
import re
from datetime import datetime as dt
from urllib.parse import urlparse

# Import logic from app_ocr
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
# Directorio para documentos con error
ERRORS_DIR = os.path.join(project_root, "errores")

# Variable global para estado de procesamiento
is_processing_active = False

# Mapeo de tipos de documento
TIPOS_DOCUMENTO = {
    'PTG': 'Permiso de Trabajo General',
    'GM': 'Formulario de Gastos Menores',
    'FAC': 'Factura',
    'GD': 'Guía de Despacho',
    'DOC': 'Documento'
}

# Asegurar que existan todos los directorios
os.makedirs(app_ocr.RUTA_PENDIENTES, exist_ok=True)
os.makedirs(app_ocr.RUTA_PROCESADOS, exist_ok=True)
os.makedirs(app_ocr.RUTA_LOG, exist_ok=True)
os.makedirs(ERRORS_DIR, exist_ok=True)

# ===== FUNCIONES PARA MANEJO DE RUTAS =====

def convertir_url_sharepoint_a_ruta(url_sharepoint):
    """Convierte URL de SharePoint a ruta local sincronizada con OneDrive"""
    try:
        # Patrones comunes de SharePoint
        patrones = [
            r'https?://([^/]+)\.sharepoint\.com/:f:/s/([^/]+)',
            r'https?://([^/]+)\.sharepoint\.com/sites/([^/]+)',
            r'https?://([^/]+)\.sharepoint\.com/([^/]+)'
        ]
        
        # Obtener el nombre del sitio de la URL
        for patron in patrones:
            match = re.search(patron, url_sharepoint)
            if match:
                sitio = match.group(2) if len(match.groups()) > 1 else match.group(1)
                # Buscar en las rutas comunes de OneDrive
                onedrive_base = os.path.expanduser(f"~/OneDrive - {sitio.split('/')[0] if '/' in sitio else sitio}")
                if os.path.exists(onedrive_base):
                    return onedrive_base
                
                # Buscar en OneDrive empresarial
                onedrive_business = os.path.expanduser(f"~/OneDrive - {sitio}")
                if os.path.exists(onedrive_business):
                    return onedrive_business
        
        # Si no se encuentra, retornar la URL original
        return url_sharepoint
    except Exception as e:
        print(f"Error convirtiendo URL de SharePoint: {e}")
        return url_sharepoint

def normalizar_ruta(ruta):
    """Normaliza cualquier tipo de ruta a un formato válido para el sistema"""
    if not ruta:
        return ruta
    
    ruta = ruta.strip()
    
    # Si es una URL de SharePoint, convertir a ruta local
    if 'sharepoint.com' in ruta.lower() or 'sharepoint' in ruta.lower():
        ruta_convertida = convertir_url_sharepoint_a_ruta(ruta)
        if ruta_convertida != ruta:
            app_ocr.registro_log("ruta", f"URL de SharePoint convertida: {ruta} -> {ruta_convertida}")
            return ruta_convertida
    
    # Si es una ruta UNC (\\servidor\recurso)
    if ruta.startswith('\\\\'):
        return ruta
    
    # Si es una unidad de red (Z:\carpeta)
    if re.match(r'^[A-Za-z]:\\', ruta):
        return os.path.normpath(ruta)
    
    # Si es una ruta relativa o absoluta normal
    if os.path.isabs(ruta):
        return os.path.normpath(ruta)
    
    # Si es una ruta relativa, convertir a absoluta
    return os.path.abspath(ruta)

def validar_y_crear_ruta(ruta):
    """Valida y crea la ruta si es necesario"""
    try:
        ruta_normalizada = normalizar_ruta(ruta)
        
        # Para rutas UNC o unidades de red, no intentar crear
        if ruta_normalizada.startswith('\\\\'):
            if not os.path.exists(ruta_normalizada):
                app_ocr.registro_log("ruta", f"Ruta UNC no accesible: {ruta_normalizada}")
            return ruta_normalizada
        
        # Para rutas locales, crear directorio
        os.makedirs(ruta_normalizada, exist_ok=True)
        return ruta_normalizada
    except Exception as e:
        app_ocr.registro_log("ruta", f"Error validando ruta {ruta}: {str(e)}")
        return ruta

# ===== FUNCIONES AUXILIARES =====
def obtener_error_del_log(filename):
    """Extraer el error específico del archivo desde los logs"""
    try:
        log_file = os.path.join(app_ocr.RUTA_LOG, "ejecucion_log.txt")
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                logs = f.readlines()
                # Buscar el error más reciente relacionado con este archivo
                for line in reversed(logs):
                    if filename in line and ('error' in line.lower() or 'fallo' in line.lower() or 'exception' in line.lower()):
                        # Extraer mensaje de error
                        if 'Error:' in line:
                            return line.split('Error:')[-1].strip()[:150]
                        elif 'error' in line.lower():
                            return line.strip()[:150]
                        elif 'Exception:' in line:
                            return line.split('Exception:')[-1].strip()[:150]
        return "Error en procesamiento OCR - Revise los logs para más detalles"
    except:
        return "Error desconocido en procesamiento"

def extraer_datos_permiso_trabajo(data_ocr):
    """Extrae datos específicos de un Permiso de Trabajo General"""
    datos = {
        'tipo': 'Permiso de Trabajo General',
        'numero_permiso': '',
        'fecha_inicio': '',
        'hora_inicio': '',
        'fecha_termino': '',
        'hora_termino': '',
        'responsable_nombre': '',
        'empresa_contratista': '',
        'supervisor_contratista': '',
        'verificador_nombre': '',
        'verificador_firma': '',
        'conformidad': '',
        'fecha_cierre': '',
        'hora_cierre': ''
    }
    
    # Buscar número de permiso
    patrones_numero = [
        r'[Nn]úmero\s*[dD]e\s*[Pp]ermiso\s*:?\s*([A-Z0-9\-]+)',
        r'[Pp]ermiso\s*[Nn]°\s*:?\s*([A-Z0-9\-]+)',
        r'[Pp]ermiso\s*[Nn]úmero\s*:?\s*([A-Z0-9\-]+)',
        r'PT[-\s]*([A-Z0-9\-]+)'
    ]
    
    for patron in patrones_numero:
        match = re.search(patron, data_ocr.get('texto_completo', ''))
        if match:
            datos['numero_permiso'] = match.group(1).strip()
            break
    
    # Buscar fechas y horas de inicio/término
    # Patrón para fecha (DD/MM/YYYY o DD-MM-YYYY)
    patron_fecha = r'(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})'
    
    texto = data_ocr.get('texto_completo', '')
    
    # Buscar inicio
    for patron in [
        r'[Ii]nicio\s*:?\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})\s*(\d{1,2}:\d{2})',
        r'[Ff]echa\s*[Yy]\s*[Hh]ora\s*[Ii]nicio\s*:?\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})\s*(\d{1,2}:\d{2})',
        r'[Ii]nicio\s*[Dd]el\s*[Tt]rabajo\s*:?\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})\s*(\d{1,2}:\d{2})'
    ]:
        match = re.search(patron, texto)
        if match:
            datos['fecha_inicio'] = match.group(1)
            datos['hora_inicio'] = match.group(2)
            break
    
    # Buscar término
    for patron in [
        r'[Tt]érmi[nt]o\s*:?\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})\s*(\d{1,2}:\d{2})',
        r'[Ff]echa\s*[Yy]\s*[Hh]ora\s*[Tt]érmi[nt]o\s*:?\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})\s*(\d{1,2}:\d{2})'
    ]:
        match = re.search(patron, texto)
        if match:
            datos['fecha_termino'] = match.group(1)
            datos['hora_termino'] = match.group(2)
            break
    
    # Buscar responsable
    patrones_responsable = [
        r'[Rr]esponsable\s*[Dd]el\s*[Tt]rabajo\s*:?\s*([^\n]+)',
        r'[Nn]ombre\s*[Rr]esponsable\s*:?\s*([^\n]+)',
        r'[Rr]esponsable\s*:?\s*([^\n]+)'
    ]
    for patron in patrones_responsable:
        match = re.search(patron, texto)
        if match:
            datos['responsable_nombre'] = match.group(1).strip()
            break
    
    # Buscar empresa contratista
    patrones_empresa = [
        r'[Ee]mpresa\s*[Cc]ontratista\s*:?\s*([^\n]+)',
        r'[Cc]ontratista\s*:?\s*([^\n]+)',
        r'[Ee]mpresa\s*:?\s*([^\n]+)'
    ]
    for patron in patrones_empresa:
        match = re.search(patron, texto)
        if match:
            datos['empresa_contratista'] = match.group(1).strip()
            break
    
    # Buscar supervisor
    patrones_supervisor = [
        r'[Ss]upervisor\s*[Dd]el\s*[Cc]ontratista\s*:?\s*([^\n]+)',
        r'[Ss]upervisor\s*:?\s*([^\n]+)'
    ]
    for patron in patrones_supervisor:
        match = re.search(patron, texto)
        if match:
            datos['supervisor_contratista'] = match.group(1).strip()
            break
    
    # Buscar verificador
    patrones_verificador = [
        r'[Vv]erifica[dr]\s*:?\s*([^\n]+)',
        r'[Nn]ombre\s*[Dd]el\s*[Vv]erifica[dr]\s*:?\s*([^\n]+)'
    ]
    for patron in patrones_verificador:
        match = re.search(patron, texto)
        if match:
            datos['verificador_nombre'] = match.group(1).strip()
            break
    
    # Buscar conformidad
    if re.search(r'[Cc]onforme', texto):
        datos['conformidad'] = 'Conforme'
    elif re.search(r'[Nn]o\s*[Cc]onforme', texto):
        datos['conformidad'] = 'No conforme'
    
    # Buscar fecha de cierre
    for patron in [
        r'[Cc]ierre\s*:?\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})\s*(\d{1,2}:\d{2})',
        r'[Ff]echa\s*[Yy]\s*[Hh]ora\s*[Cc]ierre\s*:?\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})\s*(\d{1,2}:\d{2})'
    ]:
        match = re.search(patron, texto)
        if match:
            datos['fecha_cierre'] = match.group(1)
            datos['hora_cierre'] = match.group(2)
            break
    
    return datos

def extraer_datos_gasto_menor(data_ocr):
    """Extrae datos específicos de un Formulario de Gastos Menores"""
    datos = {
        'tipo': 'Formulario de Gastos Menores',
        'folio': '',
        'fecha': '',
        'rut_solicitante': '',
        'nombre_solicitante': '',
        'monto_total': '',
        'moneda': 'CLP',
        'descripcion': '',
        'centro_costo': '',
        'aprobador': '',
        'estado': ''
    }
    
    texto = data_ocr.get('texto_completo', '')
    
    # Buscar folio o número de formulario
    patrones_folio = [
        r'[Ff]ormulario\s*[Nn]°\s*:?\s*([A-Z0-9\-]+)',
        r'[Ff]olio\s*:?\s*([A-Z0-9\-]+)',
        r'[Nn]úmero\s*:?\s*([A-Z0-9\-]+)'
    ]
    for patron in patrones_folio:
        match = re.search(patron, texto)
        if match:
            datos['folio'] = match.group(1).strip()
            break
    
    # Buscar fecha
    patron_fecha = r'[Ff]echa\s*:?\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})'
    match = re.search(patron_fecha, texto)
    if match:
        datos['fecha'] = match.group(1)
    
    # Buscar RUT del solicitante
    patron_rut = r'[Rr]ut\s*:?\s*(\d{1,2}\.\d{3}\.\d{3}[-][\dkK])'
    match = re.search(patron_rut, texto)
    if match:
        datos['rut_solicitante'] = match.group(1)
    else:
        # RUT sin puntos
        patron_rut2 = r'[Rr]ut\s*:?\s*(\d{7,8}[-][\dkK])'
        match = re.search(patron_rut2, texto)
        if match:
            datos['rut_solicitante'] = match.group(1)
    
    # Buscar nombre del solicitante
    patrones_nombre = [
        r'[Ss]olicitante\s*:?\s*([^\n]+)',
        r'[Nn]ombre\s*[Ss]olicitante\s*:?\s*([^\n]+)'
    ]
    for patron in patrones_nombre:
        match = re.search(patron, texto)
        if match:
            datos['nombre_solicitante'] = match.group(1).strip()
            break
    
    # Buscar monto total
    patron_monto = r'[Mm]onto\s*[Tt]otal\s*:?\s*\$?\s*([\d\.,]+)'
    match = re.search(patron_monto, texto)
    if match:
        monto_str = match.group(1).replace('.', '').replace(',', '')
        if monto_str.isdigit():
            datos['monto_total'] = int(monto_str)
        else:
            datos['monto_total'] = monto_str
    
    # Buscar moneda
    if re.search(r'USD|\$[^C]', texto):
        datos['moneda'] = 'USD'
    elif re.search(r'UF', texto):
        datos['moneda'] = 'UF'
    
    # Buscar descripción
    patrones_desc = [
        r'[Dd]escripción\s*:?\s*([^\n]+)',
        r'[Dd]etalle\s*:?\s*([^\n]+)',
        r'[Cc]oncepto\s*:?\s*([^\n]+)'
    ]
    for patron in patrones_desc:
        match = re.search(patron, texto)
        if match:
            datos['descripcion'] = match.group(1).strip()
            break
    
    # Buscar centro de costo
    patron_centro = r'[Cc]entro\s*[Dd]e\s*[Cc]osto\s*:?\s*([^\n]+)'
    match = re.search(patron_centro, texto)
    if match:
        datos['centro_costo'] = match.group(1).strip()
    
    # Buscar aprobador
    patron_aprobador = r'[Aa]prueba\s*:?\s*([^\n]+)'
    match = re.search(patron_aprobador, texto)
    if match:
        datos['aprobador'] = match.group(1).strip()
    
    # Buscar estado
    if re.search(r'[Aa]probado', texto):
        datos['estado'] = 'Aprobado'
    elif re.search(r'[Rr]echazado', texto):
        datos['estado'] = 'Rechazado'
    elif re.search(r'[Pp]endiente', texto):
        datos['estado'] = 'Pendiente'
    
    return datos

def detectar_tipo_documento(data_ocr):
    """Detecta el tipo de documento basado en el texto OCR"""
    texto = data_ocr.get('texto_completo', '').upper()
    
    # Detectar Permiso de Trabajo General
    palabras_ptg = ['PERMISO DE TRABAJO', 'PERMISO TRABAJO', 'AUTORIZACIÓN TRABAJO', 
                    'TRABAJO GENERAL', 'RESPONSABLE DEL TRABAJO', 'CONTRATISTA']
    coincidencias_ptg = sum(1 for palabra in palabras_ptg if palabra in texto)
    
    # Detectar Formulario de Gastos Menores
    palabras_gm = ['GASTOS MENORES', 'GASTO MENOR', 'SOLICITUD DE GASTO', 
                   'FORMULARIO DE GASTOS', 'MONTO TOTAL', 'SOLICITANTE']
    coincidencias_gm = sum(1 for palabra in palabras_gm if palabra in texto)
    
    # Detectar Factura
    palabras_fac = ['FACTURA', 'FACTURA ELECTRÓNICA', 'RUT', 'MONTO NETO', 'IVA']
    coincidencias_fac = sum(1 for palabra in palabras_fac if palabra in texto)
    
    # Detectar Guía de Despacho
    palabras_gd = ['GUÍA DE DESPACHO', 'GUIA DESPACHO', 'RUT DESTINATARIO', 'BODEGA']
    coincidencias_gd = sum(1 for palabra in palabras_gd if palabra in texto)
    
    # Determinar tipo basado en coincidencias
    tipos = [
        ('ptg', coincidencias_ptg),
        ('gm', coincidencias_gm),
        ('fac', coincidencias_fac),
        ('gd', coincidencias_gd)
    ]
    
    # Ordenar por número de coincidencias (mayor primero)
    tipos.sort(key=lambda x: x[1], reverse=True)
    
    if tipos[0][1] >= 2:  # Al menos 2 coincidencias para considerar
        return tipos[0][0]
    
    return 'desconocido'

def procesar_documento_segun_tipo(tipo, data_ocr, filename, carpeta_destino):
    """Procesa el documento según su tipo y extrae los datos correspondientes"""
    
    if tipo == 'ptg':
        datos = extraer_datos_permiso_trabajo(data_ocr)
        nombre_base = f"PTG_{datos['numero_permiso']}" if datos['numero_permiso'] else f"PTG_{filename.replace('.pdf', '')}"
        
    elif tipo == 'gm':
        datos = extraer_datos_gasto_menor(data_ocr)
        nombre_base = f"GM_{datos['folio']}" if datos['folio'] else f"GM_{filename.replace('.pdf', '')}"
        
    elif tipo == 'fac':
        from app_ocr import extraer_datos_factura
        datos = extraer_datos_factura(data_ocr)
        nombre_base = f"FAC_{datos['folio']}" if datos.get('folio') else f"FAC_{filename.replace('.pdf', '')}"
        
    elif tipo == 'gd':
        from app_ocr import extraer_datos_guia
        datos = extraer_datos_guia(data_ocr)
        nombre_base = f"GD_{datos['folio']}" if datos.get('folio') else f"GD_{filename.replace('.pdf', '')}"
    else:
        datos = {'tipo': 'Desconocido', 'texto_extraido': data_ocr.get('texto_completo', '')[:500]}
        nombre_base = f"DOC_{filename.replace('.pdf', '')}"
    
    return datos, nombre_base

# ===== ENDPOINTS EXISTENTES (MODIFICADOS) =====

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Obtener estadísticas del sistema incluyendo erróneos"""
    try:
        # Contar pendientes
        pendientes = 0
        ruta_pendientes = normalizar_ruta(app_ocr.RUTA_PENDIENTES)
        if os.path.exists(ruta_pendientes):
            pendientes = len([f for f in os.listdir(ruta_pendientes) if f.lower().endswith('.pdf')])
        
        # Contar procesados (carpetas)
        procesados = 0
        ruta_procesados = normalizar_ruta(app_ocr.RUTA_PROCESADOS)
        if os.path.exists(ruta_procesados):
            procesados = len([d for d in os.listdir(ruta_procesados) if os.path.isdir(os.path.join(ruta_procesados, d))])
        
        # Contar erróneos
        erroneos = 0
        if os.path.exists(ERRORS_DIR):
            erroneos = len([f for f in os.listdir(ERRORS_DIR) if f.lower().endswith('.pdf')])
        
        activo = app_ocr.hay_proceso_activo()
        
        return jsonify({
            'pendientes': pendientes,
            'procesados': procesados,
            'erroneos': erroneos,
            'activo': activo,
            'intervalo': app_ocr.INTERVALO_MINUTOS
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
                if f.lower().endswith('.pdf'):
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
                    except Exception as e:
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
    """Obtener lista de documentos procesados exitosamente con detección mejorada de tipos"""
    try:
        docs = []
        ruta_procesados = normalizar_ruta(app_ocr.RUTA_PROCESADOS)
        
        print(f"[OCR] Buscando documentos procesados en: {ruta_procesados}")
        
        if os.path.exists(ruta_procesados):
            for carpeta in os.listdir(ruta_procesados):
                ruta_carpeta = os.path.join(ruta_procesados, carpeta)
                
                if os.path.isdir(ruta_carpeta):
                    tipo = "Desconocido"
                    fecha = ""
                    rut_destino = ""
                    folio_detectado = carpeta
                    datos_especificos = {}
                    
                    print(f"[OCR] Procesando carpeta: {carpeta}")
                    
                    # Buscar archivos en la carpeta
                    for archivo in os.listdir(ruta_carpeta):
                        # Método 1: Detectar tipo por el prefijo del archivo PDF
                        if archivo.endswith('.pdf'):
                            if archivo.startswith('PTG_'):
                                tipo = "Permiso de Trabajo General"
                                print(f"   [+] Detectado por prefijo PTG_: {archivo}")
                            elif archivo.startswith('GM_'):
                                tipo = "Formulario de Gastos Menores"
                                print(f"   [+] Detectado por prefijo GM_: {archivo}")
                            elif archivo.startswith('FAC_'):
                                tipo = "Factura"
                                print(f"   [+] Detectado por prefijo FAC_: {archivo}")
                            elif archivo.startswith('GD_'):
                                tipo = "Guia"
                                print(f"   [+] Detectado por prefijo GD_: {archivo}")
                            elif archivo.startswith('DOC_'):
                                tipo = "Documento"
                                print(f"   [+] Detectado por prefijo DOC_: {archivo}")
                        
                        # Método 2: Detectar tipo por el contenido del XML (más preciso)
                        if archivo.endswith('.xml'):
                            xml_path = os.path.join(ruta_carpeta, archivo)
                            try:
                                import xml.etree.ElementTree as ET
                                
                                tree = ET.parse(xml_path)
                                root_xml = tree.getroot()
                                
                                # Obtener tipo_doc del XML
                                tipo_doc_elem = root_xml.find('tipo_doc')
                                if tipo_doc_elem is not None and tipo_doc_elem.text:
                                    tipo_xml = tipo_doc_elem.text.strip()
                                    if tipo_xml == "PTG":
                                        tipo = "Permiso de Trabajo General"
                                        print(f"   [XML] Detectado por XML tipo_doc=PTG: {archivo}")
                                    elif tipo_xml == "GM":
                                        tipo = "Formulario de Gastos Menores"
                                        print(f"   [XML] Detectado por XML tipo_doc=GM: {archivo}")
                                    elif tipo_xml == "FAC":
                                        tipo = "Factura"
                                        print(f"   [XML] Detectado por XML tipo_doc=FAC: {archivo}")
                                    elif tipo_xml == "GD":
                                        tipo = "Guia"
                                        print(f"   [XML] Detectado por XML tipo_doc=GD: {archivo}")
                                
                                # Obtener datos específicos según tipo
                                if tipo == "Permiso de Trabajo General":
                                    num_permiso = root_xml.find('numero_permiso')
                                    if num_permiso is not None:
                                        datos_especificos['numero_permiso'] = num_permiso.text
                                    
                                    responsable = root_xml.find('responsable_nombre')
                                    if responsable is not None:
                                        datos_especificos['responsable'] = responsable.text
                                    
                                    empresa = root_xml.find('empresa_contratista')
                                    if empresa is not None:
                                        datos_especificos['empresa'] = empresa.text
                                    
                                    conformidad = root_xml.find('conformidad')
                                    if conformidad is not None:
                                        datos_especificos['conformidad'] = conformidad.text
                                
                                elif tipo == "Formulario de Gastos Menores":
                                    monto = root_xml.find('monto_total')
                                    if monto is not None:
                                        datos_especificos['monto'] = monto.text
                                    
                                    solicitante = root_xml.find('nombre_solicitante')
                                    if solicitante is not None:
                                        datos_especificos['solicitante'] = solicitante.text
                                    
                                    descripcion = root_xml.find('descripcion')
                                    if descripcion is not None:
                                        datos_especificos['descripcion'] = descripcion.text
                                
                                # Obtener RUT destino
                                rut_elem = root_xml.find('rut_destino')
                                if rut_elem is not None:
                                    rut_destino = rut_elem.text or ""
                                    if rut_destino:
                                        print(f"   [RUT] RUT destino: {rut_destino}")
                                
                                # Obtener fecha del documento
                                fecha_doc_elem = root_xml.find('fecha_doc')
                                if fecha_doc_elem is not None and fecha_doc_elem.text:
                                    fecha = fecha_doc_elem.text
                                    print(f"   [Fecha] Fecha documento: {fecha}")
                                    
                            except Exception as e:
                                print(f"   [WARN] Error leyendo XML {xml_path}: {e}")
                        
                        # Método 3: Buscar en JSON para más información
                        if archivo.endswith('.json'):
                            json_path = os.path.join(ruta_carpeta, archivo)
                            try:
                                with open(json_path, 'r', encoding='utf-8') as jf:
                                    data = json.load(jf)
                                    
                                    # Usar fecha del JSON si no se encontró en XML
                                    if not fecha:
                                        fecha = data.get('fecha_procesamiento', '')
                                    
                                    # Buscar tipo en entities del JSON
                                    entities = data.get('entities', [])
                                    for entity in entities:
                                        props = entity.get('properties', [])
                                        for prop in props:
                                            if prop.get('type') == 'tipo_documento':
                                                texto_tipo = prop.get('mentionText', '').upper()
                                                if 'PERMISO' in texto_tipo or 'TRABAJO' in texto_tipo:
                                                    tipo = "Permiso de Trabajo General"
                                                elif 'GASTO' in texto_tipo:
                                                    tipo = "Formulario de Gastos Menores"
                                                elif 'FACTURA' in texto_tipo:
                                                    tipo = "Factura"
                                                elif 'GUIA' in texto_tipo:
                                                    tipo = "Guia"
                                            
                                            # Buscar datos específicos
                                            if tipo == "Permiso de Trabajo General":
                                                if prop.get('type') == 'numero_permiso':
                                                    datos_especificos['numero_permiso'] = prop.get('mentionText', '')
                                                elif prop.get('type') == 'responsable':
                                                    datos_especificos['responsable'] = prop.get('mentionText', '')
                                                elif prop.get('type') == 'conformidad':
                                                    datos_especificos['conformidad'] = prop.get('mentionText', '')
                                            
                                            elif tipo == "Formulario de Gastos Menores":
                                                if prop.get('type') == 'monto_total':
                                                    datos_especificos['monto'] = prop.get('mentionText', '')
                                                elif prop.get('type') == 'solicitante':
                                                    datos_especificos['solicitante'] = prop.get('mentionText', '')
                                            
                                            if prop.get('type') == 'rut_dest' and not rut_destino:
                                                rut_destino = prop.get('mentionText', '')
                                                
                            except Exception as e:
                                print(f"   [WARN] Error leyendo JSON {json_path}: {e}")
                    
                    # Si no se encontró fecha, usar la fecha de modificación de la carpeta
                    if not fecha:
                        try:
                            mtime = os.path.getmtime(ruta_carpeta)
                            fecha = dt.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
                        except:
                            fecha = "Sin fecha"
                    
                    # Si el tipo sigue siendo Desconocido, intentar por el nombre de la carpeta
                    if tipo == "Desconocido":
                        carpeta_upper = carpeta.upper()
                        if 'PTG' in carpeta_upper:
                            tipo = "Permiso de Trabajo General"
                        elif 'GM' in carpeta_upper:
                            tipo = "Formulario de Gastos Menores"
                        elif 'FAC' in carpeta_upper or 'FACTURA' in carpeta_upper:
                            tipo = "Factura"
                        elif 'GD' in carpeta_upper or 'GUIA' in carpeta_upper:
                            tipo = "Guía"
                    
                    doc_info = {
                        'folio': folio_detectado,
                        'tipo': tipo,
                        'rut': rut_destino,
                        'fecha': fecha,
                        'archivos': os.listdir(ruta_carpeta)
                    }
                    
                    # Agregar datos específicos si existen
                    if datos_especificos:
                        doc_info['datos_especificos'] = datos_especificos
                    
                    print(f"[OK] RESULTADO: {carpeta} -> Tipo: {tipo}")
                    docs.append(doc_info)
        else:
            print(f"[ERROR] La ruta de procesados no existe: {ruta_procesados}")
        
        print(f"[INFO] Total documentos procesados encontrados: {len(docs)}")
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
        if os.path.exists(ERRORS_DIR):
            for file in os.listdir(ERRORS_DIR):
                if file.lower().endswith('.pdf'):
                    file_path = os.path.join(ERRORS_DIR, file)
                    try:
                        stat = os.stat(file_path)
                        error_msg = obtener_error_del_log(file)
                        
                        error_files.append({
                            'nombre': file,
                            'error': error_msg,
                            'fecha': dt.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                            'tamaño': f"{stat.st_size / 1024:.2f} KB"
                        })
                    except Exception as e:
                        error_files.append({
                            'nombre': file,
                            'error': "Error al leer archivo",
                            'fecha': "Sin fecha",
                            'tamaño': "Desconocido"
                        })
        
        return jsonify(error_files)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/retry-error/<path:filename>', methods=['POST'])
def retry_error_document(filename):
    """Reintentar procesar un documento que tuvo error"""
    try:
        error_file_path = os.path.join(ERRORS_DIR, filename)
        ruta_pendientes = normalizar_ruta(app_ocr.RUTA_PENDIENTES)
        pending_file_path = os.path.join(ruta_pendientes, filename)
        
        if os.path.exists(error_file_path):
            shutil.move(error_file_path, pending_file_path)
            app_ocr.registro_log("retry_error", f"Documento {filename} movido de errores a pendientes para reintento")
            return jsonify({'success': True, 'message': 'Documento enviado a procesar nuevamente'})
        else:
            return jsonify({'error': 'Archivo no encontrado'}), 404
            
    except Exception as e:
        app_ocr.registro_log("retry_error", f"Error al reintentar {filename}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/retry-all-errors', methods=['POST'])
def retry_all_errors():
    """Reintentar todos los documentos con error"""
    try:
        moved_count = 0
        ruta_pendientes = normalizar_ruta(app_ocr.RUTA_PENDIENTES)
        
        if os.path.exists(ERRORS_DIR):
            for filename in os.listdir(ERRORS_DIR):
                if filename.lower().endswith('.pdf'):
                    error_path = os.path.join(ERRORS_DIR, filename)
                    pending_path = os.path.join(ruta_pendientes, filename)
                    shutil.move(error_path, pending_path)
                    moved_count += 1
                    app_ocr.registro_log("retry_all_errors", f"Documento {filename} movido de errores a pendientes")
        
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
        file_path = os.path.join(ERRORS_DIR, filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            app_ocr.registro_log("delete_error", f"Documento {filename} eliminado de la carpeta de errores")
            return jsonify({'success': True, 'message': 'Documento eliminado'})
        else:
            return jsonify({'error': 'Archivo no encontrado'}), 404
    except Exception as e:
        app_ocr.registro_log("delete_error", f"Error al eliminar {filename}: {str(e)}")
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

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Subir archivo PDF"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file part'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400
            
        if file and file.filename.lower().endswith('.pdf'):
            filename = app_ocr.secure_filename(file.filename)
            ruta_pendientes = normalizar_ruta(app_ocr.RUTA_PENDIENTES)
            filepath = os.path.join(ruta_pendientes, filename)
            file.save(filepath)
            app_ocr.registro_log("api_upload", f"Archivo subido: {filename}")
            return jsonify({'success': True, 'message': 'File uploaded successfully'})
            
        return jsonify({'error': 'Invalid file type, only PDF allowed'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/process', methods=['POST'])
def trigger_process():
    """Iniciar proceso OCR manualmente"""
    try:
        if app_ocr.hay_proceso_activo():
            return jsonify({'success': False, 'message': 'Proceso ya está activo'})
            
        def run_ocr():
            try:
                app_ocr.ejecutar_con_reintentos()
            except Exception as e:
                app_ocr.registro_log("api_process_error", str(e))
                
        thread = threading.Thread(target=run_ocr)
        thread.daemon = True
        thread.start()
        
        return jsonify({'success': True, 'message': 'Procesamiento OCR iniciado en segundo plano'})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/download/pdf/<folio>', methods=['GET'])
def download_pdf(folio):
    """Descargar PDF procesado"""
    try:
        ruta_procesados = normalizar_ruta(app_ocr.RUTA_PROCESADOS)
        folder = os.path.join(ruta_procesados, folio)
        if not os.path.exists(folder):
            return jsonify({'error': 'Not found'}), 404
            
        for f in os.listdir(folder):
            if f.endswith('.pdf'):
                return send_from_directory(folder, f, as_attachment=True)
                
        return jsonify({'error': 'PDF not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500
        
@app.route('/api/download/xml/<folio>', methods=['GET'])
def download_xml(folio):
    """Descargar XML procesado"""
    try:
        ruta_procesados = normalizar_ruta(app_ocr.RUTA_PROCESADOS)
        folder = os.path.join(ruta_procesados, folio)
        if not os.path.exists(folder):
            return jsonify({'error': 'Not found'}), 404
            
        for f in os.listdir(folder):
            if f.endswith('.xml'):
                return send_from_directory(folder, f, as_attachment=True)
                
        return jsonify({'error': 'XML not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/open/<folio>', methods=['POST'])
def open_folder(folio):
    """Abrir carpeta del documento procesado"""
    try:
        ruta_procesados = normalizar_ruta(app_ocr.RUTA_PROCESADOS)
        folder = os.path.join(ruta_procesados, folio)
        if not os.path.exists(folder):
            return jsonify({'error': 'Folder not found'}), 404
            
        os.startfile(folder)
        return jsonify({'success': True})
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
                if 'ruta_destino' in data:
                    app_ocr.RUTA_DESTINO = normalizar_ruta(data['ruta_destino'])
                    validar_y_crear_ruta(app_ocr.RUTA_DESTINO)
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
            'ruta_destino': app_ocr.RUTA_DESTINO,
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
        'ruta_destino': app_ocr.RUTA_DESTINO,
        'intervalo': app_ocr.INTERVALO_MINUTOS,
        'persistente': os.path.exists(CONFIG_FILE)
    })

@app.route('/api/config', methods=['POST'])
def update_config():
    """Actualizar configuración - SOPORTA TODO TIPO DE RUTAS"""
    try:
        data = request.json
        
        if 'ruta_pendientes' in data:
            ruta = normalizar_ruta(data['ruta_pendientes'])
            app_ocr.RUTA_PENDIENTES = validar_y_crear_ruta(ruta)
            app_ocr.registro_log("config", f"Ruta pendientes actualizada: {app_ocr.RUTA_PENDIENTES}")
            
        if 'ruta_procesados' in data:
            ruta = normalizar_ruta(data['ruta_procesados'])
            app_ocr.RUTA_PROCESADOS = validar_y_crear_ruta(ruta)
            app_ocr.registro_log("config", f"Ruta procesados actualizada: {app_ocr.RUTA_PROCESADOS}")
            
        if 'ruta_destino' in data:
            ruta = normalizar_ruta(data['ruta_destino'])
            app_ocr.RUTA_DESTINO = validar_y_crear_ruta(ruta)
            app_ocr.registro_log("config", f"Ruta destino actualizada: {app_ocr.RUTA_DESTINO}")
            
        if 'intervalo' in data:
            app_ocr.INTERVALO_MINUTOS = int(data['intervalo'])
            app_ocr.registro_log("config", f"Intervalo actualizado: {app_ocr.INTERVALO_MINUTOS} minutos")
        
        if data.get('guardar_permanente'):
            save_config_to_file()
        elif os.path.exists(CONFIG_FILE) and data.get('borrar_permanente'):
            os.remove(CONFIG_FILE)
            
        return jsonify({'success': True, 'message': 'Configuración actualizada correctamente'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/browse', methods=['POST'])
def browse_folder():
    """Abrir diálogo para seleccionar carpeta"""
    try:
        import tkinter as tk
        from tkinter import filedialog
        
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        
        folder_path = filedialog.askdirectory()
        root.destroy()
        
        if folder_path:
            ruta_normalizada = os.path.normpath(folder_path)
            return jsonify({'path': ruta_normalizada})
        return jsonify({'path': None})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Nuevo endpoint para validar rutas
@app.route('/api/validate-path', methods=['POST'])
def validate_path():
    """Validar si una ruta es accesible"""
    try:
        data = request.json
        ruta = data.get('path', '')
        
        if not ruta:
            return jsonify({'valid': False, 'message': 'Ruta vacía'})
        
        ruta_normalizada = normalizar_ruta(ruta)
        
        # Verificar si la ruta existe
        if os.path.exists(ruta_normalizada):
            return jsonify({
                'valid': True,
                'message': 'Ruta accesible',
                'normalized_path': ruta_normalizada,
                'is_directory': os.path.isdir(ruta_normalizada)
            })
        else:
            # Intentar crear el directorio
            try:
                os.makedirs(ruta_normalizada, exist_ok=True)
                return jsonify({
                    'valid': True,
                    'message': 'Ruta creada exitosamente',
                    'normalized_path': ruta_normalizada,
                    'is_directory': True
                })
            except Exception as create_error:
                return jsonify({
                    'valid': False,
                    'message': f'No se puede acceder o crear la ruta: {str(create_error)}'
                })
    except Exception as e:
        return jsonify({'valid': False, 'message': str(e)}), 500

# Nuevos endpoints para obtener datos específicos de documentos
@app.route('/api/document-data/<folio>/<tipo>', methods=['GET'])
def get_document_data(folio, tipo):
    """Obtener datos específicos de un documento procesado"""
    try:
        ruta_procesados = normalizar_ruta(app_ocr.RUTA_PROCESADOS)
        folder = os.path.join(ruta_procesados, folio)
        
        if not os.path.exists(folder):
            return jsonify({'error': 'Documento no encontrado'}), 404
        
        # Buscar archivo XML
        datos = {}
        for archivo in os.listdir(folder):
            if archivo.endswith('.xml'):
                xml_path = os.path.join(folder, archivo)
                try:
                    import xml.etree.ElementTree as ET
                    tree = ET.parse(xml_path)
                    root = tree.getroot()
                    
                    # Extraer todos los datos según el tipo
                    for elem in root:
                        datos[elem.tag] = elem.text
                except:
                    pass
            
            elif archivo.endswith('.json'):
                json_path = os.path.join(folder, archivo)
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        datos['datos_completos'] = data
                except:
                    pass
        
        return jsonify({
            'folio': folio,
            'tipo': tipo,
            'datos': datos
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/search-documents', methods=['POST'])
def search_documents():
    """Buscar documentos por tipo, fecha o texto"""
    try:
        data = request.json
        tipo_busqueda = data.get('tipo', '')
        texto_busqueda = data.get('texto', '').lower()
        fecha_desde = data.get('fecha_desde', '')
        fecha_hasta = data.get('fecha_hasta', '')
        
        resultados = []
        ruta_procesados = normalizar_ruta(app_ocr.RUTA_PROCESADOS)
        
        if os.path.exists(ruta_procesados):
            for carpeta in os.listdir(ruta_procesados):
                ruta_carpeta = os.path.join(ruta_procesados, carpeta)
                
                if os.path.isdir(ruta_carpeta):
                    # Determinar tipo de la carpeta
                    tipo_doc = "Desconocido"
                    if carpeta.startswith('PTG_'):
                        tipo_doc = "Permiso de Trabajo General"
                    elif carpeta.startswith('GM_'):
                        tipo_doc = "Formulario de Gastos Menores"
                    elif carpeta.startswith('FAC_'):
                        tipo_doc = "Factura"
                    elif carpeta.startswith('GD_'):
                        tipo_doc = "Guía"
                    
                    # Filtrar por tipo
                    if tipo_busqueda and tipo_busqueda != tipo_doc:
                        continue
                    
                    # Buscar en archivos de texto
                    encontrado = False
                    if texto_busqueda:
                        for archivo in os.listdir(ruta_carpeta):
                            if archivo.endswith('.txt'):
                                txt_path = os.path.join(ruta_carpeta, archivo)
                                try:
                                    with open(txt_path, 'r', encoding='utf-8') as f:
                                        contenido = f.read().lower()
                                        if texto_busqueda in contenido:
                                            encontrado = True
                                            break
                                except:
                                    pass
                        if not encontrado:
                            continue
                    
                    # Filtrar por fecha
                    if fecha_desde or fecha_hasta:
                        try:
                            mtime = os.path.getmtime(ruta_carpeta)
                            fecha_carpeta = dt.fromtimestamp(mtime).strftime('%Y-%m-%d')
                            if fecha_desde and fecha_carpeta < fecha_desde:
                                continue
                            if fecha_hasta and fecha_carpeta > fecha_hasta:
                                continue
                        except:
                            pass
                    
                    resultados.append({
                        'folio': carpeta,
                        'tipo': tipo_doc,
                        'fecha': dt.fromtimestamp(os.path.getmtime(ruta_carpeta)).strftime('%Y-%m-%d %H:%M:%S') if os.path.exists(ruta_carpeta) else "Sin fecha"
                    })
        
        return jsonify({
            'total': len(resultados),
            'resultados': resultados
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ===== SCHEDULER =====
def start_scheduler():
    """Iniciar el scheduler para procesamiento automático"""
    import schedule
    import time
    
    def run_schedule():
        while True:
            schedule.run_pending()
            time.sleep(1)
    
    def scheduled_process():
        app_ocr.registro_log("scheduler", f"Ejecución automática programada")
        try:
            app_ocr.ejecutar_con_reintentos()
        except Exception as e:
            app_ocr.registro_log("scheduler", f"Error en ejecución automática: {str(e)}")
    
    schedule.every(app_ocr.INTERVALO_MINUTOS).minutes.do(scheduled_process)
    app_ocr.registro_log("scheduler", f"Scheduler iniciado cada {app_ocr.INTERVALO_MINUTOS} minutos")
    
    thread = threading.Thread(target=run_schedule)
    thread.daemon = True
    thread.start()

# ===== INICIO DE LA APLICACIÓN =====
if __name__ == '__main__':
    load_config_from_file()
    start_scheduler()
    print("=" * 60)
    print("SERVICIOS WEB OCR - BACKEND INICIADO")
    print("=" * 60)
    print(f"Servidor: http://localhost:5000")
    print(f"Pendientes: {app_ocr.RUTA_PENDIENTES}")
    print(f"Procesados: {app_ocr.RUTA_PROCESADOS}")
    print(f"Errores:    {ERRORS_DIR}")
    print(f"Intervalo:  {app_ocr.INTERVALO_MINUTOS} minutos")
    print("=" * 60)
    print("Tipos de documento soportados:")
    print("   - Permiso de Trabajo General (PTG)")
    print("   - Formulario de Gastos Menores (GM)")
    print("   - Factura (FAC)")
    print("   - Guía de Despacho (GD)")
    print("=" * 60)
    print("Soporte para rutas:")
    print("   - Rutas locales (C:\\carpeta)")
    print("   - Unidades de red (Z:\\carpeta)")
    print("   - Rutas UNC (\\\\servidor\\recurso)")
    print("   - URLs de SharePoint (convertidas automaticamente)")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)