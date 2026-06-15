
import datetime
import os
import sys
import time
import json
import shutil
import fitz
import unidecode
import schedule
import xml.etree.ElementTree as ET
import threading
from datetime import datetime
from google.cloud import documentai
from google.protobuf.json_format import MessageToDict
from google.api_core.client_options import ClientOptions
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader, PdfWriter
from dotenv import load_dotenv
import subprocess
import re


from document_processor import DocumentProcessor, configurar_tesseract
load_dotenv()

# ==================== CONFIGURACIÓN ====================
backend_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(backend_dir)

# Configuración inicial (puede ser sobrescrita por config_web.json)
RUTA_DESTINO = os.path.join(project_root, "SubirComidor")
HORA_INICIO = 0
HORA_FIN = 23
INTERVALO_MINUTOS = 5
MAX_REINTENTOS = 3
TIMEOUT_PROCESO = 1800
ARCHIVO_PROCESO = os.path.join(project_root, "proceso.txt")
ARCHIVO_ULTIMA_EJECUCION = os.path.join(project_root, "ultima_ejecucion.txt")
RUTA_PENDIENTES = os.path.join(project_root, "doc_pendientes")
RUTA_PROCESADOS = os.path.join(project_root, "doc_procesados")
RUTA_JSONS = os.path.join(project_root, "jsons")
RUTA_LOG = os.path.join(project_root, "log")

# Definir carpeta de errores
ERRORS_DIR = os.path.join(backend_dir, "errores")

# Variable global para la interfaz
app_instance = None
log_lock = threading.Lock()
STOP_REQUESTED = False

# ==================== MANEJO DE RUTAS DE RED ====================

def mapear_unidad_red(ruta_unc: str, letra_unidad: str = None) -> str:
    """
    Mapea una ruta UNC a una unidad de red local.
    
    Args:
        ruta_unc: Ruta UNC (ej: \\\\servidor\\carpeta)
        letra_unidad: Letra de unidad opcional (ej: 'Z:')
    
    Returns:
        Ruta mapeada o la ruta original si no se pudo mapear
    """
    try:
        # Si ya es una unidad de red mapeada, retornar
        if re.match(r'^[A-Za-z]:\\', ruta_unc):
            return ruta_unc
        
        # Si no es UNC, retornar original
        if not ruta_unc.startswith('\\\\'):
            return ruta_unc
        
        # Buscar letra de unidad disponible si no se especificó
        if not letra_unidad:
            letra_unidad = 'Z:'
        
        # Verificar si ya está mapeada
        unidad_path = f"{letra_unidad}\\"
        if os.path.exists(unidad_path):
            # Verificar si apunta a la misma ruta
            try:
                net_use_output = subprocess.check_output(f'net use {letra_unidad}', shell=True, text=True)
                if ruta_unc.lower() in net_use_output.lower():
                    return unidad_path
            except:
                pass
            
            # Desmapear unidad existente
            subprocess.run(f'net use {letra_unidad} /delete /y', shell=True, capture_output=True)
            time.sleep(2)
        
        # Mapear la unidad
        comando = f'net use {letra_unidad} "{ruta_unc}" /persistent:yes'
        resultado = subprocess.run(comando, shell=True, capture_output=True, text=True)
        
        if resultado.returncode == 0:
            registro_log("mapeo_red", f"✅ Unidad {letra_unidad} mapeada a {ruta_unc}")
            return unidad_path
        else:
            registro_log("mapeo_red", f"❌ Error mapeando {ruta_unc}: {resultado.stderr}")
            return ruta_unc
            
    except Exception as e:
        registro_log("mapeo_red", f"Error en mapeo: {e}")
        return ruta_unc

def verificar_acceso_red(ruta: str, reintentos: int = 3) -> bool:
    """
    Verifica si se puede acceder a una ruta de red.
    
    Args:
        ruta: Ruta a verificar
        reintentos: Número de reintentos
    
    Returns:
        True si es accesible, False si no
    """
    for intento in range(reintentos):
        try:
            if os.path.exists(ruta):
                # Intentar crear/leer un archivo de prueba
                test_file = os.path.join(ruta, f".test_access_{datetime.now().strftime('%Y%m%d_%H%M%S')}.tmp")
                with open(test_file, 'w') as f:
                    f.write("test")
                if os.path.exists(test_file):
                    os.remove(test_file)
                return True
        except Exception as e:
            registro_log("acceso_red", f"Intento {intento + 1} fallido para {ruta}: {e}")
            if intento < reintentos - 1:
                time.sleep(5)
    return False

def conectar_con_credenciales(ruta_unc: str, usuario: str = None, contrasena: str = None) -> bool:
    """
    Conecta a una ruta UNC con credenciales específicas.
    
    Args:
        ruta_unc: Ruta UNC
        usuario: Usuario (formato: dominio\\usuario o usuario@dominio)
        contrasena: Contraseña
    
    Returns:
        True si se conectó exitosamente
    """
    try:
        if usuario and contrasena:
            comando = f'net use "{ruta_unc}" /user:{usuario} "{contrasena}" /persistent:yes'
        else:
            comando = f'net use "{ruta_unc}" /persistent:yes'
        
        resultado = subprocess.run(comando, shell=True, capture_output=True, text=True)
        
        if resultado.returncode == 0:
            registro_log("conexion_red", f"✅ Conectado a {ruta_unc}")
            return True
        else:
            registro_log("conexion_red", f"❌ Error conectando a {ruta_unc}: {resultado.stderr}")
            return False
            
    except Exception as e:
        registro_log("conexion_red", f"Error: {e}")
        return False

def convertir_sharepoint_a_unc(url_sharepoint: str) -> str:
    """Convierte URL de SharePoint a ruta UNC sincronizada"""
    try:
        # Patrones comunes de SharePoint Online
        patrones = [
            r'https?://([^/]+)\.sharepoint\.com/(?:sites/)?([^/]+)/?(.*)',
            r'https?://([^/]+)\.sharepoint\.com/:f:/s/([^/]+)/?(.*)',
        ]
        
        for patron in patrones:
            match = re.search(patron, url_sharepoint)
            if match:
                dominio = match.group(1)
                sitio = match.group(2)
                ruta_relativa = match.group(3) if len(match.groups()) > 2 else ""
                
                # Construir ruta UNC para OneDrive sincronizado
                onedrive_base = os.path.expanduser(f"~/OneDrive - {dominio.split('.')[0]}")
                
                if os.path.exists(onedrive_base):
                    ruta_completa = os.path.join(onedrive_base, sitio, ruta_relativa.replace('/', '\\'))
                    return ruta_completa
                
                # Alternativa: buscar en OneDrive empresarial
                onedrive_business = os.path.expanduser(f"~/OneDrive - {sitio}")
                if os.path.exists(onedrive_business):
                    return os.path.join(onedrive_business, ruta_relativa.replace('/', '\\'))
        
        return url_sharepoint
    except Exception as e:
        registro_log("sharepoint", f"Error convirtiendo URL: {e}")
        return url_sharepoint

def normalizar_ruta_red(ruta: str, letra_unidad: str = None) -> str:
    """
    Normaliza cualquier tipo de ruta (local, UNC, SharePoint) a una ruta accesible.
    
    Args:
        ruta: Ruta original
        letra_unidad: Letra de unidad para mapeo (opcional)
    
    Returns:
        Ruta normalizada y accesible
    """
    if not ruta:
        return ruta
    
    ruta = ruta.strip()
    
    # Manejar URLs de SharePoint
    if 'sharepoint.com' in ruta.lower():
        ruta_convertida = convertir_sharepoint_a_unc(ruta)
        if ruta_convertida != ruta:
            registro_log("normalizar", f"SharePoint convertido: {ruta} -> {ruta_convertida}")
            ruta = ruta_convertida
    
    # Manejar rutas UNC
    if ruta.startswith('\\\\'):
        # Intentar mapear a una unidad
        ruta_mapeada = mapear_unidad_red(ruta, letra_unidad)
        return ruta_mapeada
    
    # Manejar rutas con unidades de red
    if re.match(r'^[A-Za-z]:\\', ruta):
        # Verificar si la unidad existe
        unidad = ruta[:2]
        if not os.path.exists(unidad):
            registro_log("normalizar", f"Unidad {unidad} no existe, intentando reconectar...")
            # Intentar reconectar unidades de red
            subprocess.run(f'net use {unidad} /persistent:yes', shell=True, capture_output=True)
            time.sleep(2)
    
    return os.path.normpath(ruta)

def asegurar_acceso_ruta(ruta: str, credenciales: dict = None) -> tuple:
    """
    Asegura que se pueda acceder a una ruta, intentando diferentes métodos.
    
    Args:
        ruta: Ruta a asegurar
        credenciales: Diccionario con 'usuario' y 'contrasena'
    
    Returns:
        (ruta_accesible, mensaje)
    """
    ruta_normalizada = normalizar_ruta_red(ruta)
    
    # Verificar acceso
    if verificar_acceso_red(ruta_normalizada):
        return (ruta_normalizada, "Acceso OK")
    
    # Si hay credenciales, intentar conectar
    if credenciales and ruta.startswith('\\\\'):
        if conectar_con_credenciales(ruta, credenciales.get('usuario'), credenciales.get('contrasena')):
            if verificar_acceso_red(ruta_normalizada):
                return (ruta_normalizada, "Conectado con credenciales")
    
    # Intentar mapear con diferentes letras
    if ruta.startswith('\\\\'):
        for letra in ['Z', 'Y', 'X', 'W']:
            ruta_mapeada = mapear_unidad_red(ruta, f"{letra}:")
            if verificar_acceso_red(ruta_mapeada):
                return (ruta_mapeada, f"Mapeado como {letra}:")
    
    return (ruta_normalizada, "Acceso limitado - verificar red")

# ==================== MAPEO DE TIPOS DE DOCUMENTO ====================
TIPOS_DOCUMENTO = {
    'PTG': 'Permiso de Trabajo General',
    'GM': 'Formulario de Gastos Menores',
    'FAC': 'Factura',
    'GD': 'Guía de Despacho',
    'DOC': 'Documento'
}

# Palabras clave para detección de tipos
PALABRAS_CLAVE_PTG = [
    'PERMISO DE TRABAJO', 'PERMISO TRABAJO', 'AUTORIZACIÓN TRABAJO',
    'TRABAJO GENERAL', 'RESPONSABLE DEL TRABAJO', 'CONTRATISTA',
    'SUPERVISOR', 'VERIFICADOR', 'CONFORMIDAD', 'PERMISO', 'WORK PERMIT'
]

PALABRAS_CLAVE_GM = [
    'GASTOS MENORES', 'GASTO MENOR', 'SOLICITUD DE GASTO',
    'FORMULARIO DE GASTOS', 'MONTO TOTAL', 'SOLICITANTE',
    'CENTRO DE COSTO', 'APROBADOR', 'EXPENSE', 'MINOR EXPENSE'
]

PALABRAS_CLAVE_FAC = [
    'FACTURA', 'FACTURA ELECTRÓNICA', 'RUT', 'MONTO NETO', 'IVA',
    'NUMERO DE FACTURA', 'FOLIO', 'SII', 'INVOICE'
]

PALABRAS_CLAVE_GD = [
    'GUÍA DE DESPACHO', 'GUIA DESPACHO', 'RUT DESTINATARIO', 'BODEGA',
    'NUMERO DE GUIA', 'DESPACHADOR', 'DESPACHO', 'WAYBILL'
]

# ==================== FUNCIONES DE LOGGING ====================
def registro_log(proceso: str, dato: str) -> None:
    try:
        with log_lock:
            os.makedirs(RUTA_LOG, exist_ok=True)
            with open(os.path.join(RUTA_LOG, "ejecucion_log.txt"), 'a', encoding='utf-8') as file:
                fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                file.write(f"{fecha_hora} - {proceso} - {dato}\n")
            print(f"{fecha_hora} - {proceso} - {dato}")
    except Exception as e:
        print(f"Error al escribir log: {e}")

def agregar_log_ui(mensaje: str):
    global app_instance
    if app_instance:
        app_instance._agregar_log_ui(mensaje)

# ==================== FUNCIONES DE DETECCIÓN DE TIPO ====================
def detectar_tipo_documento(texto: str) -> str:
    """Detecta el tipo de documento basado en el texto OCR"""
    if not texto:
        return "DOC"
    
    texto_upper = unidecode.unidecode(texto.upper())
    
    # Contar coincidencias para cada tipo
    coincidencias_ptg = sum(1 for palabra in PALABRAS_CLAVE_PTG if palabra in texto_upper)
    coincidencias_gm = sum(1 for palabra in PALABRAS_CLAVE_GM if palabra in texto_upper)
    coincidencias_fac = sum(1 for palabra in PALABRAS_CLAVE_FAC if palabra in texto_upper)
    coincidencias_gd = sum(1 for palabra in PALABRAS_CLAVE_GD if palabra in texto_upper)
    
    # Diccionario de coincidencias
    tipos = [
        ('PTG', coincidencias_ptg),
        ('GM', coincidencias_gm),
        ('FAC', coincidencias_fac),
        ('GD', coincidencias_gd)
    ]
    
    # Ordenar por número de coincidencias (mayor primero)
    tipos.sort(key=lambda x: x[1], reverse=True)
    
    # Si hay al menos 2 coincidencias, considerar el tipo
    if tipos[0][1] >= 2:
        return tipos[0][0]
    elif tipos[0][1] >= 1 and tipos[0][0] in ['FAC', 'GD']:
        return tipos[0][0]
    
    return "DOC"

def obtener_prefijo_por_tipo(tipo_documento: str) -> str:
    """Obtiene el prefijo según el tipo de documento"""
    tipo_upper = tipo_documento.upper() if tipo_documento else ""
    if "PTG" in tipo_upper or "PERMISO" in tipo_upper:
        return "PTG"
    elif "GM" in tipo_upper or "GASTO" in tipo_upper:
        return "GM"
    elif "FAC" in tipo_upper or "FACTURA" in tipo_upper:
        return "FAC"
    elif "GD" in tipo_upper or "GUIA" in tipo_upper or "DESPACHO" in tipo_upper:
        return "GD"
    else:
        return "DOC"

# ==================== FUNCIONES DE EXTRACCIÓN ESPECÍFICAS ====================

def extraer_datos_permiso_trabajo(entities: list, texto_completo: str) -> dict:
    """Extrae datos específicos de un Permiso de Trabajo General"""
    datos = {
        'tipo': 'PTG',
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
    
    # Buscar en entities de Document AI
    for entity in entities:
        props = entity.get('properties', [])
        entity_type = entity.get('type', '')
        
        if entity_type == 'numero_permiso':
            datos['numero_permiso'] = entity.get('mentionText', '')
        elif entity_type == 'fecha_inicio':
            datos['fecha_inicio'] = entity.get('mentionText', '')
        elif entity_type == 'responsable':
            datos['responsable_nombre'] = entity.get('mentionText', '')
        elif entity_type == 'empresa_contratista':
            datos['empresa_contratista'] = entity.get('mentionText', '')
        elif entity_type == 'supervisor':
            datos['supervisor_contratista'] = entity.get('mentionText', '')
        elif entity_type == 'verificador':
            datos['verificador_nombre'] = entity.get('mentionText', '')
        elif entity_type == 'conformidad':
            datos['conformidad'] = entity.get('mentionText', '')
        
        for prop in props:
            prop_type = prop.get('type', '')
            prop_text = prop.get('mentionText', '')
            if prop_type == 'numero_permiso':
                datos['numero_permiso'] = prop_text
            elif prop_type == 'fecha_inicio':
                datos['fecha_inicio'] = prop_text
            elif prop_type == 'responsable':
                datos['responsable_nombre'] = prop_text
            elif prop_type == 'empresa_contratista':
                datos['empresa_contratista'] = prop_text
            elif prop_type == 'supervisor':
                datos['supervisor_contratista'] = prop_text
    
    # Búsqueda con regex en texto completo si no se encontró en entities
    if not datos['numero_permiso']:
        patrones = [
            r'[Nn]úmero\s*[Dd]e\s*[Pp]ermiso\s*:?\s*([A-Z0-9\-]+)',
            r'[Pp]ermiso\s*[Nn]°\s*:?\s*([A-Z0-9\-]+)',
            r'PT[-\s]*([A-Z0-9\-]+)'
        ]
        for patron in patrones:
            match = re.search(patron, texto_completo)
            if match:
                datos['numero_permiso'] = match.group(1).strip()
                break
    
    if not datos['fecha_inicio']:
        patron_fecha = r'[Ii]nicio\s*:?\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})'
        match = re.search(patron_fecha, texto_completo)
        if match:
            datos['fecha_inicio'] = match.group(1)
    
    # Determinar conformidad
    if not datos['conformidad']:
        if re.search(r'[Cc]onforme', texto_completo):
            datos['conformidad'] = 'Conforme'
        elif re.search(r'[Nn]o\s*[Cc]onforme', texto_completo):
            datos['conformidad'] = 'No conforme'
    
    return datos

def extraer_datos_gasto_menor(entities: list, texto_completo: str) -> dict:
    """Extrae datos específicos de un Formulario de Gastos Menores"""
    datos = {
        'tipo': 'GM',
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
    
    # Buscar en entities de Document AI
    for entity in entities:
        props = entity.get('properties', [])
        entity_type = entity.get('type', '')
        
        if entity_type == 'folio' or entity_type == 'id_folio':
            datos['folio'] = entity.get('mentionText', '')
        elif entity_type == 'fecha':
            datos['fecha'] = entity.get('mentionText', '')
        elif entity_type == 'rut':
            datos['rut_solicitante'] = entity.get('mentionText', '')
        elif entity_type == 'solicitante':
            datos['nombre_solicitante'] = entity.get('mentionText', '')
        elif entity_type == 'monto_total':
            datos['monto_total'] = entity.get('mentionText', '')
        elif entity_type == 'descripcion':
            datos['descripcion'] = entity.get('mentionText', '')
        elif entity_type == 'centro_costo':
            datos['centro_costo'] = entity.get('mentionText', '')
        elif entity_type == 'aprobador':
            datos['aprobador'] = entity.get('mentionText', '')
        
        for prop in props:
            prop_type = prop.get('type', '')
            prop_text = prop.get('mentionText', '')
            if prop_type == 'folio' or prop_type == 'id_folio':
                datos['folio'] = prop_text
            elif prop_type == 'fecha':
                datos['fecha'] = prop_text
            elif prop_type == 'rut':
                datos['rut_solicitante'] = prop_text
            elif prop_type == 'solicitante':
                datos['nombre_solicitante'] = prop_text
            elif prop_type == 'monto_total':
                datos['monto_total'] = prop_text
            elif prop_type == 'descripcion':
                datos['descripcion'] = prop_text
    
    # Búsqueda con regex si no se encontró en entities
    if not datos['folio']:
        patron_folio = r'[Ff]ormulario\s*[Nn]°\s*:?\s*([A-Z0-9\-]+)'
        match = re.search(patron_folio, texto_completo)
        if match:
            datos['folio'] = match.group(1).strip()
    
    if not datos['fecha']:
        patron_fecha = r'[Ff]echa\s*:?\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})'
        match = re.search(patron_fecha, texto_completo)
        if match:
            datos['fecha'] = match.group(1)
    
    if not datos['rut_solicitante']:
        patron_rut = r'[Rr]ut\s*:?\s*(\d{1,2}\.\d{3}\.\d{3}[-][\dkK])'
        match = re.search(patron_rut, texto_completo)
        if match:
            datos['rut_solicitante'] = match.group(1)
    
    # Buscar monto
    if not datos['monto_total']:
        patron_monto = r'[Mm]onto\s*[Tt]otal\s*:?\s*\$?\s*([\d\.,]+)'
        match = re.search(patron_monto, texto_completo)
        if match:
            datos['monto_total'] = match.group(1)
    
    return datos

# ==================== FUNCIONES DE XML ====================
def buscar_datos_xml(lista: list, tipo: str) -> str:
    if not lista:
        return ""
    for diccionario in lista:
        if 'properties' in diccionario:
            for propiedades in diccionario['properties']:
                if propiedades.get('type') == tipo:
                    return propiedades.get('mentionText', "")
    return ""

def generar_xml(datos, paginas, ruta, nombre_documento, firmado, tipo_documento_detectado="DOC") -> str:
    try:
        raiz = ET.Element("data")
        
        entities = datos if isinstance(datos, list) else []
        
        # Extraer según el tipo detectado
        if tipo_documento_detectado == "PTG":
            datos_ptg = extraer_datos_permiso_trabajo(entities, "")
            
            tipo_doc = ET.SubElement(raiz, "tipo_doc")
            tipo_doc.text = "PTG"
            
            numero_permiso = ET.SubElement(raiz, "numero_permiso")
            numero_permiso.text = datos_ptg.get('numero_permiso', '')
            
            fecha_inicio = ET.SubElement(raiz, "fecha_inicio")
            fecha_inicio.text = datos_ptg.get('fecha_inicio', '')
            
            hora_inicio = ET.SubElement(raiz, "hora_inicio")
            hora_inicio.text = datos_ptg.get('hora_inicio', '')
            
            fecha_termino = ET.SubElement(raiz, "fecha_termino")
            fecha_termino.text = datos_ptg.get('fecha_termino', '')
            
            hora_termino = ET.SubElement(raiz, "hora_termino")
            hora_termino.text = datos_ptg.get('hora_termino', '')
            
            responsable_nombre = ET.SubElement(raiz, "responsable_nombre")
            responsable_nombre.text = datos_ptg.get('responsable_nombre', '')
            
            empresa_contratista = ET.SubElement(raiz, "empresa_contratista")
            empresa_contratista.text = datos_ptg.get('empresa_contratista', '')
            
            supervisor_contratista = ET.SubElement(raiz, "supervisor_contratista")
            supervisor_contratista.text = datos_ptg.get('supervisor_contratista', '')
            
            verificador_nombre = ET.SubElement(raiz, "verificador_nombre")
            verificador_nombre.text = datos_ptg.get('verificador_nombre', '')
            
            conformidad = ET.SubElement(raiz, "conformidad")
            conformidad.text = datos_ptg.get('conformidad', '')
            
            fecha_cierre = ET.SubElement(raiz, "fecha_cierre")
            fecha_cierre.text = datos_ptg.get('fecha_cierre', '')
            
            hora_cierre = ET.SubElement(raiz, "hora_cierre")
            hora_cierre.text = datos_ptg.get('hora_cierre', '')
            
            folio_valor = datos_ptg.get('numero_permiso', nombre_documento)
            
        elif tipo_documento_detectado == "GM":
            datos_gm = extraer_datos_gasto_menor(entities, "")
            
            tipo_doc = ET.SubElement(raiz, "tipo_doc")
            tipo_doc.text = "GM"
            
            folio_elem = ET.SubElement(raiz, "folio")
            folio_elem.text = datos_gm.get('folio', nombre_documento)
            
            fecha_doc = ET.SubElement(raiz, "fecha_doc")
            fecha_doc.text = datos_gm.get('fecha', '')
            
            rut_solicitante = ET.SubElement(raiz, "rut_solicitante")
            rut_solicitante.text = datos_gm.get('rut_solicitante', '')
            
            nombre_solicitante = ET.SubElement(raiz, "nombre_solicitante")
            nombre_solicitante.text = datos_gm.get('nombre_solicitante', '')
            
            monto_total = ET.SubElement(raiz, "monto_total")
            monto_total.text = datos_gm.get('monto_total', '')
            
            moneda = ET.SubElement(raiz, "moneda")
            moneda.text = datos_gm.get('moneda', 'CLP')
            
            descripcion = ET.SubElement(raiz, "descripcion")
            descripcion.text = datos_gm.get('descripcion', '')
            
            centro_costo = ET.SubElement(raiz, "centro_costo")
            centro_costo.text = datos_gm.get('centro_costo', '')
            
            aprobador = ET.SubElement(raiz, "aprobador")
            aprobador.text = datos_gm.get('aprobador', '')
            
            estado = ET.SubElement(raiz, "estado")
            estado.text = datos_gm.get('estado', '')
            
            folio_valor = datos_gm.get('folio', nombre_documento)
            
        else:
            # Tipos originales: FAC, GD, DOC
            tipo_doc_text = buscar_datos_xml(entities, 'tipo_folio')
            if tipo_doc_text:
                if "FACTURA" in tipo_doc_text.upper():
                    tipo_doc_text = "FAC"
                elif "GUIA" in tipo_doc_text.upper() or "DESPACHO" in tipo_doc_text.upper():
                    tipo_doc_text = "GD"
                else:
                    tipo_doc_text = ""
            else:
                tipo_doc_text = ""
            
            rut_emisor_text = buscar_datos_xml(entities, 'rut_emp')
            rut_destino_text = buscar_datos_xml(entities, 'rut_dest')
            folio_text = buscar_datos_xml(entities, 'id_folio')
            orden_compra_text = buscar_datos_xml(entities, 'orden_compra_detalle')
            total_text = buscar_datos_xml(entities, 'valor_total')
            fecha_doc_text = buscar_datos_xml(entities, 'fecha_emision_folio')
            
            if total_text:
                total_text = total_text.replace(".", "")
            if not folio_text:
                folio_text = nombre_documento
            
            tipo_doc = ET.SubElement(raiz, "tipo_doc")
            tipo_doc.text = tipo_doc_text
            rut_emisor = ET.SubElement(raiz, "rut_emisor")
            rut_emisor.text = rut_emisor_text or ""
            rut_destino = ET.SubElement(raiz, "rut_destino")
            rut_destino.text = rut_destino_text or ""
            folio_elem = ET.SubElement(raiz, "folio")
            folio_elem.text = folio_text
            orden_compra = ET.SubElement(raiz, "orden_compra")
            orden_compra.text = orden_compra_text or ""
            total_elem = ET.SubElement(raiz, "total")
            total_elem.text = total_text or ""
            fecha_doc = ET.SubElement(raiz, "fecha_doc")
            fecha_doc.text = fecha_doc_text or ""
            
            folio_valor = folio_text
        
        os.makedirs(ruta, exist_ok=True)
        ruta_completa = os.path.join(ruta, f"{nombre_documento}.xml")
        ET.ElementTree(raiz).write(ruta_completa, encoding="utf-8", xml_declaration=True)
        
        return f'{tipo_documento_detectado}|{datetime.now().strftime("%Y-%m-%d")}|{nombre_documento}.xml|{ruta_completa}|'
    except Exception as e:
        print(f"Error generando XML: {e}")
        return f'ERROR|{datetime.now()}|{nombre_documento}.xml|{ruta}|RUT_ERROR'

# ==================== FUNCIONES DE PROCESAMIENTO ====================
def transformar_pdf_a_imagen(ruta_pdf: str, numero_pagina: int) -> str:
    doc = fitz.open(ruta_pdf)
    pagina = doc[numero_pagina - 1] if numero_pagina > 0 else doc[0]
    imagen = pagina.get_pixmap()
    path_imagen = ruta_pdf.replace(".PDF", '.png').replace(".pdf", '.png')
    imagen.save(path_imagen)
    doc.close()
    return path_imagen

def buscar_datos_ocr(lista: list, tipo: str) -> str:
    for diccionario in lista:
        for propiedades in diccionario.get('properties', []):
            if propiedades.get('type') == tipo:
                return propiedades.get('mentionText', '')
    return ''

def enviar_a_destino_final(origen_pdf: str, origen_xml: str, folio: str, tipo_documento: str) -> None:
    try:
        # Normalizar ruta destino para red
        ruta_destino_normalizada = normalizar_ruta_red(RUTA_DESTINO)
        
        # Crear carpeta con número de folio dentro del destino final
        carpeta_folio_destino = os.path.join(ruta_destino_normalizada, folio)
        os.makedirs(carpeta_folio_destino, exist_ok=True)
        prefijo = obtener_prefijo_por_tipo(tipo_documento)
        nombre_con_prefijo = f"{prefijo}_{folio}"
        
        if os.path.exists(origen_pdf):
            shutil.copy2(origen_pdf, os.path.join(carpeta_folio_destino, f"{nombre_con_prefijo}.pdf"))
        if os.path.exists(origen_xml):
            shutil.copy2(origen_xml, os.path.join(carpeta_folio_destino, f"{nombre_con_prefijo}.xml"))
        
        registro_log("enviar_a_destino", f"Enviados en carpeta '{folio}': {nombre_con_prefijo}.pdf y .xml")
        agregar_log_ui(f"📤 Enviado a destino en carpeta: {folio}")
        
        # Forzar sincronización con SharePoint/OneDrive
        forzar_sincronizacion_onedrive(ruta_destino_normalizada)
        forzar_sincronizacion_onedrive(RUTA_PENDIENTES)
        
    except Exception as e:
        registro_log("enviar_a_destino", f"Error: {e}")

def limpiar_carpeta_procesados(ruta_procesados: str) -> None:
    try:
        if not os.path.exists(ruta_procesados):
            return
        for elemento in os.listdir(ruta_procesados):
            ruta_elemento = os.path.join(ruta_procesados, elemento)
            if os.path.isfile(ruta_elemento) and elemento.endswith(('.png', '.jpg', '.jpeg', '.tmp')):
                os.remove(ruta_elemento)
    except Exception as e:
        registro_log("limpieza_procesados", f"Error: {e}")

def forzar_sincronizacion_onedrive(ruta_carpeta):
    """Forzar a OneDrive a sincronizar la carpeta"""
    try:
        # Método 1: Usar el ejecutable de OneDrive
        onedrive_exe = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\OneDrive\OneDrive.exe")
        if os.path.exists(onedrive_exe):
            os.system(f'"{onedrive_exe}" /reset')
            time.sleep(2)
            
        # Método 2: Crear un archivo temporal para forzar detección de cambios
        archivo_temp = os.path.join(ruta_carpeta, ".sync_trigger.txt")
        with open(archivo_temp, 'w') as f:
            f.write(f"Sincronización forzada {datetime.now()}")
        time.sleep(1)
        if os.path.exists(archivo_temp):
            os.remove(archivo_temp)
            
        registro_log("sincronizacion", f"Forzada sincronización en: {ruta_carpeta}")
        return True
    except Exception as e:
        registro_log("sincronizacion", f"Error forzando sincronización: {e}")
        return False

# ==================== FUNCIÓN PRINCIPAL DE OCR ====================
def analisis_ocr(file_path: str, numero_pagina: int, ruta: str, nombre_archivo: str, arreglo_procesados: list, pdf_original_path: str = None):
    try:
        registro_log("analisis_ocr", f"Iniciando OCR para: {nombre_archivo}")
        agregar_log_ui(f"🔍 Procesando: {nombre_archivo}")
        
        ruta_proyecto = os.path.dirname(os.path.abspath(__file__))
        ruta_imagen_pdf = transformar_pdf_a_imagen(file_path, numero_pagina)
        
        credentials_path = os.path.join(ruta_proyecto, "credentials.json")
        if not os.path.exists(credentials_path):
            registro_log("analisis_ocr", "ERROR: No se encuentra credentials.json")
            agregar_log_ui("❌ ERROR: No se encuentra credentials.json")
            return None
        
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
        
        project_id = os.getenv("OCR_PROJECT_ID")
        processor_id = os.getenv("OCR_PROCESSOR_ID")
        mime_type = os.getenv("OCR_MIME_TYPE", "application/pdf")
        location = os.getenv("OCR_LOCATION", "us")
        
        if not all([project_id, processor_id, location]):
            registro_log("analisis_ocr", "ERROR: Faltan variables de entorno")
            agregar_log_ui("❌ ERROR: Revisar archivo .env (OCR_PROJECT_ID, OCR_PROCESSOR_ID)")
            return None
        
        opts = ClientOptions(api_endpoint=f"{location}-documentai.googleapis.com")
        client = documentai.DocumentProcessorServiceClient(client_options=opts)
        name = client.processor_path(project_id, location, processor_id)
        
        with open(file_path, "rb") as image:
            image_content = image.read()
        
        raw_document = documentai.RawDocument(content=image_content, mime_type=mime_type)
        request = documentai.ProcessRequest(name=name, raw_document=raw_document)
        result = client.process_document(request=request)
        formato = MessageToDict(result.document._pb)
        
        # Obtener texto completo para análisis
        texto_completo = formato.get('text', '')
        
        # Detectar tipo de documento
        tipo_documento_detectado = detectar_tipo_documento(texto_completo)
        registro_log("analisis_ocr", f"Tipo detectado: {TIPOS_DOCUMENTO.get(tipo_documento_detectado, 'Desconocido')}")
        
        # Extraer folio según el tipo
        if tipo_documento_detectado == "PTG":
            datos_extraidos = extraer_datos_permiso_trabajo(formato.get('entities', []), texto_completo)
            folio = datos_extraidos.get('numero_permiso', '')
        elif tipo_documento_detectado == "GM":
            datos_extraidos = extraer_datos_gasto_menor(formato.get('entities', []), texto_completo)
            folio = datos_extraidos.get('folio', '')
        else:
            folio = buscar_datos_ocr(formato.get('entities', []), 'id_folio')
        
        if not folio:
            folio = f"SIN_FOLIO_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        registro_log("analisis_ocr", f"Folio extraído: {folio}")
        
        nombre_documento = folio
        
        nombre_json = f'{folio}.json'
        os.makedirs(RUTA_JSONS, exist_ok=True)
        ruta_json = os.path.join(RUTA_JSONS, nombre_json)
        
        datos_json = {
            "nombre_original": nombre_archivo,
            "folio": folio,
            "tipo_documento": TIPOS_DOCUMENTO.get(tipo_documento_detectado, 'Desconocido'),
            "fecha_procesamiento": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "entities": formato.get('entities', []),
            "texto_completo": texto_completo[:5000]
        }
        
        with open(ruta_json, 'w', encoding='utf-8') as f:
            json.dump(datos_json, f, ensure_ascii=False, indent=2)
        
        # Normalizar ruta de procesados para red
        ruta_procesados_normalizada = normalizar_ruta_red(RUTA_PROCESADOS)
        os.makedirs(ruta_procesados_normalizada, exist_ok=True)
        carpeta_folio = os.path.join(ruta_procesados_normalizada, folio)
        os.makedirs(carpeta_folio, exist_ok=True)
        
        if pdf_original_path and os.path.exists(pdf_original_path):
            pdf_origen = pdf_original_path
        elif os.path.exists(file_path):
            pdf_origen = file_path
        else:
            pdf_origen = None
        
        registro_resultado = generar_xml(formato.get('entities', []), numero_pagina, carpeta_folio, nombre_documento, '', tipo_documento_detectado)
        
        if registro_resultado and '|' in registro_resultado:
            partes = registro_resultado.split('|')
            tipo_documento = partes[0]
            ruta_xml = partes[3]
            
            prefijo = obtener_prefijo_por_tipo(tipo_documento_detectado)
            nombre_con_prefijo = f"{prefijo}_{folio}"
            
            if pdf_origen:
                pdf_destino = os.path.join(carpeta_folio, f"{nombre_con_prefijo}.pdf")
                shutil.copy2(pdf_origen, pdf_destino)
            
            xml_original = os.path.join(carpeta_folio, f"{nombre_documento}.xml")
            xml_con_prefijo = os.path.join(carpeta_folio, f"{nombre_con_prefijo}.xml")
            if os.path.exists(xml_original):
                os.rename(xml_original, xml_con_prefijo)
                ruta_xml = xml_con_prefijo
            
            # Copiar JSON a la carpeta del folio
            if os.path.exists(ruta_json):
                shutil.copy2(ruta_json, os.path.join(carpeta_folio, f"{nombre_con_prefijo}.json"))
            
            if pdf_origen and os.path.exists(pdf_origen) and os.path.exists(ruta_xml):
                enviar_a_destino_final(pdf_origen, ruta_xml, folio, tipo_documento_detectado)
            
            try:
                if os.path.exists(ruta_imagen_pdf):
                    os.remove(ruta_imagen_pdf)
            except:
                pass
            
            arreglo_procesados.append({'folio': folio, 'tipo': TIPOS_DOCUMENTO.get(tipo_documento_detectado, 'Desconocido')})
            registro_log("analisis_ocr", f"✅ Documento procesado: {folio} ({TIPOS_DOCUMENTO.get(tipo_documento_detectado, 'Desconocido')})")
            agregar_log_ui(f"✅ Procesado: {folio} ({TIPOS_DOCUMENTO.get(tipo_documento_detectado, 'Desconocido')})")
        
        return None
    except Exception as e:
        registro_log("analisis_ocr", f"Error: {e}")
        agregar_log_ui(f"❌ Error en {nombre_archivo}: {str(e)[:80]}")
        return e

# ==================== FUNCIONES DE MANEJO DE DOCUMENTOS ====================
def separar_documentos(documento) -> list:
    documento_pdf = PdfReader(open(documento, "rb"))
    documentos_salida = []
    for numero, pagina in enumerate(documento_pdf.pages, 1):
        salida = PdfWriter()
        salida.add_page(pagina)
        documento_salida = f"{documento[:-4]}_{numero}.pdf"
        with open(documento_salida, "wb") as output_stream:
            salida.write(output_stream)
        documentos_salida.append(documento_salida)
    return documentos_salida

def analizar_documento(documento, ruta, archivo, arreglo_procesados, pdf_original_temp):
    listado_documentos = separar_documentos(documento)
    for numero_pagina, doc in enumerate(listado_documentos, 1):
        analisis_ocr(doc, numero_pagina, ruta, archivo, arreglo_procesados, pdf_original_temp)
    time.sleep(1)
    carpeta_temp = os.path.dirname(documento)
    if carpeta_temp and carpeta_temp != os.getcwd() and "temp_procesamiento" in carpeta_temp:
        try:
            shutil.rmtree(carpeta_temp)
        except:
            pass

def cargar_documento(archivo) -> tuple:
    if hasattr(archivo, 'filename'):
        nombre_archivo = archivo.filename
    else:
        nombre_archivo = str(getattr(archivo, 'name', ''))
        nombre_archivo = nombre_archivo.replace('\\', '/')
        nombre_archivo = nombre_archivo.split('/')[-1] if '/' in nombre_archivo else nombre_archivo
    
    if archivo and nombre_archivo.lower().endswith('.pdf'):
        nombre_archivo_seguro = secure_filename(nombre_archivo)
        carpeta_temp = os.path.join(os.getcwd(), "temp_procesamiento")
        os.makedirs(carpeta_temp, exist_ok=True)
        nombre_base = os.path.splitext(nombre_archivo_seguro)[0]
        ruta_archivo = os.path.join(carpeta_temp, nombre_archivo_seguro)
        if hasattr(archivo, 'read'):
            with open(ruta_archivo, 'wb') as nuevo_archivo:
                nuevo_archivo.write(archivo.read())
        else:
            shutil.copy2(archivo, ruta_archivo)
        return (ruta_archivo, carpeta_temp, nombre_base)
    return (None, None, None)

def procesar_documentos_pendientes(ruta_local) -> None:
    # Normalizar ruta de pendientes para red
    ruta_local_normalizada = normalizar_ruta_red(ruta_local)
    
    if not os.path.exists(ruta_local_normalizada):
        registro_log("procesar_documentos_pendientes", f"La ruta no existe: {ruta_local_normalizada}")
        return
    
    archivos_pdf = [f for f in os.listdir(ruta_local_normalizada) if f.lower().endswith('.pdf')]
    if len(archivos_pdf) == 0:
        registro_log("procesar_documentos_pendientes", "No hay documentos PDF para procesar")
        return
    
    registro_log("procesar_documentos_pendientes", f"Total de PDFs: {len(archivos_pdf)}")
    agregar_log_ui(f"📄 Iniciando procesamiento de {len(archivos_pdf)} documento(s)")
    archivos_procesados = []
    
    for idx, archivo in enumerate(archivos_pdf, 1):
        if hay_solicitud_detencion():
            registro_log("procesar_documentos_pendientes", "🛑 Procesamiento detenido por solicitud")
            agregar_log_ui("🛑 Procesamiento detenido")
            break
            
        ruta_archivo = os.path.join(ruta_local_normalizada, archivo)
        registro_log("procesar_documentos_pendientes", f"Procesando [{idx}/{len(archivos_pdf)}]: {archivo}")
        agregar_log_ui(f"🔄 [{idx}/{len(archivos_pdf)}] Procesando: {archivo[:50]}")
        
        try:
            with open(ruta_archivo, 'rb') as archivo_ocr:
                ruta_archivo_proc, carpeta_temp, nombre_archivo = cargar_documento(archivo_ocr)
                if ruta_archivo_proc:
                    analizar_documento(ruta_archivo_proc, carpeta_temp, nombre_archivo, archivos_procesados, ruta_archivo_proc)
            
            if os.path.exists(ruta_archivo):
                os.remove(ruta_archivo)
                registro_log("procesar_documentos_pendientes", f"Eliminado original: {archivo}")
        except Exception as e:
            registro_log("procesar_documentos_pendientes", f"Error con {archivo}: {e}")
            agregar_log_ui(f"❌ Error con {archivo}: {str(e)[:80]}")
            continue
        
        temp_path = os.path.join(os.getcwd(), "temp_procesamiento")
        if os.path.exists(temp_path):
            try:
                shutil.rmtree(temp_path)
            except:
                pass
    
    limpiar_carpeta_procesados(RUTA_PROCESADOS)
    registro_log("procesar_documentos_pendientes", f"✅ Completado. Procesados: {len(archivos_pdf)} documentos")
    agregar_log_ui(f"✅ Procesamiento completado. Total: {len(archivos_pdf)} documento(s)")

# ==================== FUNCIONES DE CONTROL ====================
def contar_pdfs_en_carpeta(ruta):
    try:
        ruta_normalizada = normalizar_ruta_red(ruta)
        if not os.path.exists(ruta_normalizada):
            return 0
        return len([f for f in os.listdir(ruta_normalizada) if f.lower().endswith('.pdf')])
    except:
        return 0

def hay_proceso_activo():
    try:
        if os.path.exists(ARCHIVO_PROCESO):
            with open(ARCHIVO_PROCESO, 'r', encoding='utf-8') as file:
                content = file.read().strip()
                if content == "TRUE":
                    tiempo_modificacion = os.path.getmtime(ARCHIVO_PROCESO)
                    tiempo_actual = time.time()
                    if tiempo_actual - tiempo_modificacion > TIMEOUT_PROCESO:
                        registro_log("timeout", "Proceso detectado como colgado, liberando...")
                        with open(ARCHIVO_PROCESO, 'w', encoding='utf-8') as f:
                            f.write("FALSE")
                        return False
                    return True
    except:
        pass
    return False

def solicitar_detencion():
    global STOP_REQUESTED
    STOP_REQUESTED = True
    registro_log("sistema", "🛑 Solicitud de detención recibida")

def hay_solicitud_detencion():
    global STOP_REQUESTED
    return STOP_REQUESTED

def resetear_detencion():
    global STOP_REQUESTED
    STOP_REQUESTED = False

def ejecutar_proceso_completo():
    registro_log("proceso_completo", "Iniciando ejecución")
    
    # Normalizar rutas para red
    ruta_pendientes_normalizada = normalizar_ruta_red(RUTA_PENDIENTES)
    ruta_procesados_normalizada = normalizar_ruta_red(RUTA_PROCESADOS)
    
    os.makedirs(ruta_pendientes_normalizada, exist_ok=True)
    os.makedirs(ruta_procesados_normalizada, exist_ok=True)
    
    cantidad_pdfs = contar_pdfs_en_carpeta(ruta_pendientes_normalizada)
    registro_log("proceso_completo", f"PDFs encontrados: {cantidad_pdfs}")
    
    if cantidad_pdfs == 0:
        return False
    
    if hay_solicitud_detencion():
        registro_log("proceso_completo", "🛑 Ejecución cancelada por solicitud de detención")
        return False

    try:
        procesar_documentos_pendientes(ruta_pendientes_normalizada)
        with open(ARCHIVO_ULTIMA_EJECUCION, 'w', encoding='utf-8') as f:
            f.write(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        return True
    except Exception as e:
        registro_log("proceso_completo", f"Error: {e}")
        raise e

def ejecutar_con_reintentos():
    resetear_detencion()
    if os.path.exists(ARCHIVO_PROCESO):
        with open(ARCHIVO_PROCESO, 'w') as f:
            f.write("FALSE")
    
    for intento in range(1, MAX_REINTENTOS + 1):
        with open(ARCHIVO_PROCESO, 'w') as f:
            f.write("TRUE")
        
        try:
            resultado = ejecutar_proceso_completo()
            with open(ARCHIVO_PROCESO, 'w') as f:
                f.write("FALSE")
            return resultado
        except Exception as e:
            registro_log("ejecutor", f"Error intento {intento}: {e}")
            with open(ARCHIVO_PROCESO, 'w') as f:
                f.write("FALSE")
            if intento < MAX_REINTENTOS:
                time.sleep(30 * intento)
    return False

# ==================== FUNCIÓN PARA ACTUALIZAR CONFIGURACIÓN ====================
def actualizar_rutas_desde_config(config_data: dict):
    """Actualiza las rutas desde la configuración web"""
    global RUTA_PENDIENTES, RUTA_PROCESADOS, RUTA_DESTINO, INTERVALO_MINUTOS
    
    try:
        if 'ruta_pendientes' in config_data and config_data['ruta_pendientes']:
            ruta = config_data['ruta_pendientes']
            ruta_normalizada = normalizar_ruta_red(ruta)
            RUTA_PENDIENTES = ruta_normalizada
            registro_log("config", f"Ruta pendientes actualizada: {RUTA_PENDIENTES}")
            
        if 'ruta_procesados' in config_data and config_data['ruta_procesados']:
            ruta = config_data['ruta_procesados']
            ruta_normalizada = normalizar_ruta_red(ruta)
            RUTA_PROCESADOS = ruta_normalizada
            registro_log("config", f"Ruta procesados actualizada: {RUTA_PROCESADOS}")
            
        if 'ruta_destino' in config_data and config_data['ruta_destino']:
            ruta = config_data['ruta_destino']
            ruta_normalizada = normalizar_ruta_red(ruta)
            RUTA_DESTINO = ruta_normalizada
            registro_log("config", f"Ruta destino actualizada: {RUTA_DESTINO}")
            
        if 'intervalo' in config_data and config_data['intervalo']:
            INTERVALO_MINUTOS = int(config_data['intervalo'])
            registro_log("config", f"Intervalo actualizado: {INTERVALO_MINUTOS} minutos")
            
        return True
    except Exception as e:
        registro_log("config", f"Error actualizando rutas: {e}")
        return False

# ==================== MAIN ====================
def inicializar_sistema():
    if os.path.exists(ARCHIVO_PROCESO):
        with open(ARCHIVO_PROCESO, 'w') as f:
            f.write("FALSE")
    
    # Normalizar rutas iniciales
    ruta_pendientes_norm = normalizar_ruta_red(RUTA_PENDIENTES)
    ruta_procesados_norm = normalizar_ruta_red(RUTA_PROCESADOS)
    ruta_destino_norm = normalizar_ruta_red(RUTA_DESTINO)
    
    os.makedirs(ruta_pendientes_norm, exist_ok=True)
    os.makedirs(ruta_procesados_norm, exist_ok=True)
    os.makedirs(ruta_destino_norm, exist_ok=True)
    os.makedirs(RUTA_JSONS, exist_ok=True)
    os.makedirs(RUTA_LOG, exist_ok=True)
    os.makedirs(ERRORS_DIR, exist_ok=True)
    
    # Verificar accesibilidad de rutas
    for nombre, ruta in [("Pendientes", ruta_pendientes_norm), 
                          ("Procesados", ruta_procesados_norm), 
                          ("Destino", ruta_destino_norm)]:
        if verificar_acceso_red(ruta):
            registro_log("sistema", f"✅ Ruta {nombre}: {ruta} - Accesible")
        else:
            registro_log("sistema", f"⚠️ Ruta {nombre}: {ruta} - Puede tener problemas de acceso")
    
    print("✅ Sistema inicializado correctamente")

def main():
    print("=" * 60)
    print("🌟 SISTEMA DE GESTIÓN DOCUMENTAL (BACKEND) v2.1 🌟")
    print("=" * 60)
    
    inicializar_sistema()
    
    print(f"\n📁 Pendientes: {normalizar_ruta_red(RUTA_PENDIENTES)}")
    print(f"📁 Procesados: {normalizar_ruta_red(RUTA_PROCESADOS)}")
    print(f"📁 Destino: {normalizar_ruta_red(RUTA_DESTINO)}")
    print("\n📄 Tipos de documento soportados:")
    print("   - Permiso de Trabajo General (PTG)")
    print("   - Formulario de Gastos Menores (GM)")
    print("   - Factura (FAC)")
    print("   - Guía de Despacho (GD)")
    print("\n🌐 Soporte para rutas de red:")
    print("   - Rutas UNC: \\\\servidor\\carpeta")
    print("   - Unidades mapeadas: Z:\\carpeta")
    print("   - SharePoint: Conversión automática")
    print("\nℹ️ Para iniciar el servidor web, ejecute 'server.py' o 'app.py'\n")

if __name__ == "__main__":
    main()