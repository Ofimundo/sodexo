import os
import json
import fitz
import shutil
import unidecode
import base64
import time

from PIL import Image, ImageDraw
from io import BytesIO
from google.cloud import documentai
from google.protobuf.json_format import MessageToDict
from google.api_core.client_options import ClientOptions
from exportar import generar_xml
from datetime import datetime
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader, PdfWriter
from dotenv import load_dotenv

load_dotenv()

# ==================== CONFIGURACIÓN ====================
RUTA_DESTINO = r"C:\Users\CONVATEC-IMPRESION\Desktop\SubirComidor"

# ==================== FUNCIONES DE LOGGING ====================

def registro_log(proceso: str, dato: str) -> None:
    """Registrar el proceso en un archivo de texto"""
    try:
        log_dir = os.path.join(os.getcwd(), "log")
        os.makedirs(log_dir, exist_ok=True)
        
        with open(os.path.join(log_dir, "ejecucion_log.txt"), 'a', encoding='utf-8') as file:
            fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            file.write(f"{fecha_hora} - {proceso} - {dato}\n")
    except Exception as e:
        print(f"Error al escribir log: {e}")

def registro_log_doc(numero_pagina: str, documentodato: str) -> None:
    """Registrar proceso de documentos en archivo específico"""
    try:
        log_dir = os.path.join(os.getcwd(), "log")
        os.makedirs(log_dir, exist_ok=True)
        
        with open(os.path.join(log_dir, "proceso_log_doc.txt"), 'a', encoding='utf-8') as file:
            fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            file.write(f"{fecha_hora} - {numero_pagina} - {documentodato}\n")
    except Exception as e:
        print(f"Error al escribir log doc: {e}")

# ==================== FUNCIONES DE UTILERÍA ====================

def limpiar_carpeta_procesados(ruta_procesados: str) -> None:
    """Limpia la carpeta doc_procesados (elimina archivos sueltos)"""
    try:
        if not os.path.exists(ruta_procesados):
            return
        
        for elemento in os.listdir(ruta_procesados):
            ruta_elemento = os.path.join(ruta_procesados, elemento)
            if os.path.isfile(ruta_elemento):
                if elemento.endswith(('.png', '.jpg', '.jpeg', '.xml', '.tmp')):
                    os.remove(ruta_elemento)
                    registro_log("limpieza_procesados", f"Archivo temporal eliminado: {elemento}")
        
        registro_log("limpieza_procesados", "Limpieza de carpeta procesados completada")
    except Exception as e:
        registro_log("limpieza_procesados", f"Error general: {e}")

def limpiar_carpeta_pendientes(ruta_pendientes: str) -> None:
    """Elimina todos los archivos de la carpeta doc_pendientes"""
    try:
        if os.path.exists(ruta_pendientes):
            for archivo in os.listdir(ruta_pendientes):
                ruta_archivo = os.path.join(ruta_pendientes, archivo)
                if os.path.isfile(ruta_archivo):
                    os.remove(ruta_archivo)
                    registro_log("limpiar_pendientes", f"Eliminado: {archivo}")
            registro_log("limpiar_pendientes", "Carpeta doc_pendientes limpiada")
    except Exception as e:
        registro_log("limpiar_pendientes", f"Error: {e}")

def obtener_prefijo_por_tipo(tipo_documento: str) -> str:
    """Devuelve el prefijo según el tipo de documento"""
    tipo_upper = tipo_documento.upper() if tipo_documento else ""
    
    if "FACTURA" in tipo_upper:
        return "FAC"
    elif "GUIA" in tipo_upper or "DESPACHO" in tipo_upper:
        return "GD"
    else:
        return "DOC"

def enviar_a_destino_final(origen_pdf: str, origen_xml: str, folio: str, tipo_documento: str) -> None:
    """Envía el PDF y XML a la ruta de destino final con nombre con prefijo"""
    try:
        # Crear la carpeta de destino si no existe
        os.makedirs(RUTA_DESTINO, exist_ok=True)
        
        # Obtener prefijo según tipo de documento
        prefijo = obtener_prefijo_por_tipo(tipo_documento)
        nombre_con_prefijo = f"{prefijo}_{folio}"
        
        # Enviar PDF
        if os.path.exists(origen_pdf):
            destino_pdf = os.path.join(RUTA_DESTINO, f"{nombre_con_prefijo}.pdf")
            shutil.copy2(origen_pdf, destino_pdf)
            registro_log("enviar_a_destino", f"PDF enviado a: {destino_pdf}")
        else:
            registro_log("enviar_a_destino", f"ERROR: No se encuentra el PDF: {origen_pdf}")
        
        # Enviar XML
        if os.path.exists(origen_xml):
            destino_xml = os.path.join(RUTA_DESTINO, f"{nombre_con_prefijo}.xml")
            shutil.copy2(origen_xml, destino_xml)
            registro_log("enviar_a_destino", f"XML enviado a: {destino_xml}")
        else:
            registro_log("enviar_a_destino", f"ERROR: No se encuentra el XML: {origen_xml}")
            
    except Exception as e:
        registro_log("enviar_a_destino", f"Error enviando archivos: {e}")

# ==================== FUNCIONES DE PROCESAMIENTO ====================

def transformar_pdf_a_imagen(ruta_pdf: str, numero_pagina: int) -> str:
    """Transforma el PDF a imagen"""
    doc = fitz.open(ruta_pdf)
    pagina = doc[numero_pagina - 1] if numero_pagina > 0 else doc[0]
    imagen = pagina.get_pixmap()
    
    path_imagen = ruta_pdf.replace(".PDF", '.png').replace(".pdf", '.png')
    imagen.save(path_imagen)
    doc.close()
    
    return path_imagen

def buscar_datos(lista: list, tipo: str) -> str:
    """Busca el tipo de documento en el XML"""
    for diccionario in lista:
        for propiedades in diccionario.get('properties', []):
            if propiedades.get('type') == tipo:
                return propiedades.get('mentionText', '')
    return ''

def comprobar_archivo_existente(arreglo: list, folio_buscar: str) -> bool:
    """Verifica si un folio ya fue procesado"""
    for elemento in arreglo:
        if elemento.get("folio") == folio_buscar:
            return True
    return False

def imagen_a_b64(data) -> str:
    """Convierte una imagen a formato base64"""
    documento_base_64 = data['pages'][0]['image']['content']
    png_bytes = base64.b64decode(documento_base_64)
    imagen = Image.open(BytesIO(png_bytes))
    
    width = data['pages'][0]['image']['width']
    height = data['pages'][0]['image']['height']
    
    for entitie in data.get('entities', []):
        for propertie in entitie.get('properties', []):
            try:
                coordinates = propertie['pageAnchor']['pageRefs'][0]['boundingPoly']['normalizedVertices']
                confidence = propertie.get('confidence', 0)
                vertices = ()
                
                for coordinate in coordinates:
                    vertices += (coordinate['x'], coordinate['y'])
                
                coordinates_rectangle = [(vertices[i] * width, vertices[i + 1] * height) for i in range(0, len(vertices), 2)]
                draw = ImageDraw.Draw(imagen)
                
                if confidence > 0.8:
                    draw.polygon(coordinates_rectangle, outline="green", width=2)
                elif confidence > 0.5:
                    draw.polygon(coordinates_rectangle, outline="orange", width=2)
                else:
                    draw.polygon(coordinates_rectangle, outline="red", width=2)
            except Exception:
                pass
    
    buffer = BytesIO()
    imagen.save(buffer, format="PNG")
    imagen_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    
    return imagen_base64

# ==================== FUNCIÓN PRINCIPAL DE OCR ====================

def analisis_ocr(file_path: str, numero_pagina: int, ruta: str, nombre_archivo: str, arreglo_procesados: list, pdf_original_path: str = None):
    """Procesa el documento con OCR y guarda el PDF en carpeta con nombre de folio con prefijo"""
    try:
        ruta_proyecto = os.getcwd()
        
        # Transformar PDF a imagen
        ruta_imagen_pdf = transformar_pdf_a_imagen(file_path, numero_pagina)
        
        # Configurar Google Document AI
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = os.path.join(ruta_proyecto, "credentials.json")
        
        project_id = os.getenv("OCR_PROJECT_ID")
        processor_id = os.getenv("OCR_PROCESSOR_ID")
        mime_type = os.getenv("OCR_MIME_TYPE")
        location = os.getenv("OCR_LOCATION")
        
        opts = ClientOptions(api_endpoint=f"{location}-documentai.googleapis.com")
        client = documentai.DocumentProcessorServiceClient(client_options=opts)
        name = client.processor_path(project_id, location, processor_id)
        
        with open(file_path, "rb") as image:
            image_content = image.read()
        
        raw_document = documentai.RawDocument(content=image_content, mime_type=mime_type)
        request = documentai.ProcessRequest(name=name, raw_document=raw_document)
        result = client.process_document(request=request)
        formato = MessageToDict(result.document._pb)
        
        # Obtener el folio del documento
        folio = buscar_datos(formato.get('entities', []), 'id_folio')
        
        if not folio:
            folio = f"SIN_FOLIO_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            registro_log("analisis_ocr", f"No se encontró folio, usando: {folio}")
        
        registro_log("analisis_ocr", f"Folio extraído: {folio}")
        
        # Determinar tipo de documento
        texto_upper = unidecode.unidecode(formato.get('text', '').upper())
        if any(tipo in texto_upper for tipo in ['FACTURA ELECTRONICA', 'FACTURA', 'HOJA DE RUTA', 'GUIA DE DESPACHO', 'COMPROBANTE DE RECEPCION', 'ORDEN DE FLETE']):
            nombre_documento = folio
        else:
            nombre_documento = 'OTROS'
        
        # ========== GUARDAR JSON EN CARPETA "jsons" ==========
        nombre_json = f'{folio}.json'
        directorio_jsons = os.path.join(ruta_proyecto, "jsons")
        os.makedirs(directorio_jsons, exist_ok=True)
        ruta_json = os.path.join(directorio_jsons, nombre_json)
        
        nueva_base64 = imagen_a_b64(formato)
        
        datos_json = {
            "nombre_original": nombre_archivo,
            "folio": folio,
            "numero_pagina": numero_pagina,
            "fecha_procesamiento": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "mimeType": formato.get('mimeType', ''),
            "image": formato.get('pages', [{}])[0].get('image', {}),
            "entities": formato.get('entities', [])
        }
        
        if 'content' in datos_json['image']:
            datos_json['image']['content'] = nueva_base64
        
        with open(ruta_json, 'w', encoding='utf-8') as f:
            json.dump(datos_json, f, ensure_ascii=False, indent=2)
        registro_log("analisis_ocr", f"JSON guardado: {nombre_json}")
        
        # ========== GUARDAR PDF EN CARPETA CON NOMBRE DE FOLIO ==========
        doc_procesados_path = r"C:\proyectos\OCR_Transversal\doc_procesados"
        os.makedirs(doc_procesados_path, exist_ok=True)
        
        # Crear carpeta con el nombre del folio
        carpeta_folio = os.path.join(doc_procesados_path, folio)
        os.makedirs(carpeta_folio, exist_ok=True)
        
        # Determinar qué PDF guardar
        if pdf_original_path and os.path.exists(pdf_original_path):
            pdf_origen = pdf_original_path
        elif os.path.exists(file_path):
            pdf_origen = file_path
        else:
            pdf_origen = None
            registro_log("analisis_ocr", f"ERROR: No se encuentra el PDF original")
        
        # ========== VALIDAR RUTA PARA EL XML ==========
        if not ruta or ruta == "":
            ruta = r"C:\proyectos\OCR_Transversal\doc_procesados"
            registro_log("analisis_ocr", f"Ruta vacía, usando: {ruta}")
        
        # ========== GENERAR XML ==========
        registro_resultado = generar_xml(formato.get('entities', []), numero_pagina, ruta, nombre_documento, '')
        
        tipo_documento = "DESCONOCIDO"
        if registro_resultado and '|' in registro_resultado:
            partes = registro_resultado.split('|')
            tipo_documento = partes[0]
            fecha = partes[1]
            mes_fecha = fecha.split('/')[1] if len(fecha.split('/')) > 1 else '01'
            ano_fecha = fecha.split('/')[2] if len(fecha.split('/')) > 2 else '2024'
            nombre_xml = partes[2]
            ruta_xml = partes[3]
            rut_receptor = partes[4] if len(partes) > 4 else ''
            
            # Verificar duplicados
            if comprobar_archivo_existente(arreglo_procesados, folio):
                registro_log("analisis_ocr", f"Duplicado: {folio}")
                if os.path.exists(ruta_xml):
                    os.remove(ruta_xml)
                pdf_path = ruta_xml.replace('.xml', '.pdf')
                if os.path.exists(pdf_path):
                    os.remove(pdf_path)
                return "Duplicado encontrado, no procesado"
            
            # Obtener prefijo según tipo de documento
            prefijo = obtener_prefijo_por_tipo(tipo_documento)
            nombre_con_prefijo = f"{prefijo}_{folio}"
            
            # Guardar PDF con nombre con prefijo en doc_procesados
            if pdf_origen:
                pdf_destino = os.path.join(carpeta_folio, f"{nombre_con_prefijo}.pdf")
                shutil.copy2(pdf_origen, pdf_destino)
                registro_log("analisis_ocr", f"PDF guardado como: {nombre_con_prefijo}.pdf")
            
            # ========== ENVIAR A DESTINO FINAL CON PREFIJO ==========
            if pdf_origen and os.path.exists(pdf_origen) and os.path.exists(ruta_xml):
                enviar_a_destino_final(pdf_origen, ruta_xml, folio, tipo_documento)
            else:
                registro_log("analisis_ocr", f"ERROR: No se pueden enviar archivos para folio {folio}")
            
            # Eliminar archivos temporales del XML
            try:
                if os.path.exists(ruta_xml):
                    os.remove(ruta_xml)
                pdf_temp = ruta_xml.replace('.xml', '.pdf')
                if os.path.exists(pdf_temp):
                    os.remove(pdf_temp)
                if os.path.exists(ruta_imagen_pdf):
                    os.remove(ruta_imagen_pdf)
            except Exception as e:
                registro_log("analisis_ocr", f"Error eliminando temporales: {e}")
            
            # Agregar a procesados
            arreglo_procesados.append({'folio': folio, 'tipo': tipo_documento})
        
        return None
        
    except Exception as e:
        registro_log("analisis_ocr", f"Error: {e}")
        return e

# ==================== FUNCIONES DE MANEJO DE DOCUMENTOS ====================

def separar_documentos(documento) -> list:
    """Separa las hojas del documento PDF"""
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
    """Analiza los documentos y guarda el PDF original"""
    listado_documentos = separar_documentos(documento)
    
    for numero_pagina, doc in enumerate(listado_documentos, 1):
        analisis_ocr(doc, numero_pagina, ruta, archivo, arreglo_procesados, pdf_original_temp)
    
    # Esperar a que se liberen los archivos
    time.sleep(1)
    
    # Eliminar carpeta temporal después de procesar
    carpeta_temp = os.path.dirname(documento)
    if carpeta_temp and carpeta_temp != os.getcwd() and "temp_procesamiento" in carpeta_temp:
        try:
            shutil.rmtree(carpeta_temp)
            registro_log("analizar_documento", f"Carpeta temporal eliminada: {carpeta_temp}")
        except Exception as e:
            registro_log("analizar_documento", f"Error eliminando carpeta: {e}")

# ==================== FUNCIONES DE CARGA Y PROCESAMIENTO PRINCIPAL ====================

def documentos_permitidos(nombre_archivo: str) -> bool:
    """Valida si el documento tiene extensión correcta"""
    return "." in nombre_archivo and nombre_archivo.rsplit('.', 1)[1].lower() == "pdf"

def cargar_documento_2(archivo) -> tuple:
    """Carga y prepara el documento para procesamiento"""
    if hasattr(archivo, 'filename'):
        nombre_archivo = archivo.filename
    else:
        nombre_archivo = str(getattr(archivo, 'name', ''))
        nombre_archivo = nombre_archivo.replace('\\', '/')
        nombre_archivo = nombre_archivo.split('/')[-1] if '/' in nombre_archivo else nombre_archivo
    
    if archivo and documentos_permitidos(nombre_archivo):
        nombre_archivo_seguro = secure_filename(nombre_archivo)
        
        # Crear carpeta temporal para procesamiento
        carpeta_temp = os.path.join(os.getcwd(), "temp_procesamiento")
        os.makedirs(carpeta_temp, exist_ok=True)
        
        nombre_base = os.path.splitext(nombre_archivo_seguro)[0]
        ruta_archivo = os.path.join(carpeta_temp, nombre_archivo_seguro)
        
        # Leer y guardar el archivo
        if hasattr(archivo, 'read'):
            with open(ruta_archivo, 'wb') as nuevo_archivo:
                nuevo_archivo.write(archivo.read())
        else:
            shutil.copy2(archivo, ruta_archivo)
        
        return (ruta_archivo, carpeta_temp, nombre_base)
    
    return (None, None, None)

def procesar_documentos_pendientes(ruta_local) -> None:
    """
    Procesa TODOS los documentos pendientes en la ruta especificada.
    Cada documento genera:
    - Una carpeta en doc_procesados con el nombre del folio
    - Un PDF dentro de esa carpeta con nombre con prefijo (FAC_ o GD_)
    - Un JSON en la carpeta jsons
    - Envía PDF y XML con prefijo a la ruta de destino final
    """
    if not os.path.exists(ruta_local):
        registro_log("procesar_documentos_pendientes", f"La ruta no existe: {ruta_local}")
        return
    
    # Obtener lista de archivos en la carpeta
    archivos = os.listdir(ruta_local)
    
    # Filtrar solo archivos PDF
    archivos_pdf = [f for f in archivos if f.lower().endswith('.pdf')]
    
    if len(archivos_pdf) == 0:
        registro_log("procesar_documentos_pendientes", "No hay documentos PDF para procesar")
        return
    
    registro_log("procesar_documentos_pendientes", f"Total de PDFs encontrados: {len(archivos_pdf)}")
    
    # Lista para almacenar folios procesados (evitar duplicados)
    archivos_procesados = []
    
    # Procesar cada PDF individualmente
    for idx, archivo in enumerate(archivos_pdf, 1):
        ruta_archivo = os.path.join(ruta_local, archivo)
        
        print(f"[{idx}/{len(archivos_pdf)}] -> Procesando: {archivo}")
        registro_log("procesar_documentos_pendientes", f"Procesando ({idx}/{len(archivos_pdf)}): {archivo}")
        
        try:
            # Abrir y procesar el documento
            with open(ruta_archivo, 'rb') as archivo_ocr:
                ruta_archivo_proc, carpeta_temp, nombre_archivo = cargar_documento_2(archivo_ocr)
                if ruta_archivo_proc:
                    analizar_documento(ruta_archivo_proc, carpeta_temp, nombre_archivo, archivos_procesados, ruta_archivo_proc)
            
            # Esperar un poco para que se liberen los archivos
            time.sleep(1)
            
            # Eliminar el PDF original de doc_pendientes después de procesarlo exitosamente
            if os.path.exists(ruta_archivo):
                os.remove(ruta_archivo)
                registro_log("procesar_documentos_pendientes", f"Eliminado de pendientes: {archivo}")
            
        except Exception as e:
            registro_log("procesar_documentos_pendientes", f"Error procesando {archivo}: {str(e)}")
            continue
        
        # Limpiar carpeta temporal después de cada documento
        temp_path = os.path.join(os.getcwd(), "temp_procesamiento")
        if os.path.exists(temp_path):
            try:
                shutil.rmtree(temp_path)
                registro_log("procesar_documentos_pendientes", "Carpeta temporal limpiada")
            except Exception as e:
                registro_log("procesar_documentos_pendientes", f"Error limpiando temporal: {e}")
    
    # Limpiar la carpeta doc_procesados (eliminar archivos sueltos)
    doc_procesados_path = r"C:\proyectos\OCR_Transversal\doc_procesados"
    limpiar_carpeta_procesados(doc_procesados_path)
    
    registro_log("procesar_documentos_pendientes", f"Procesamiento completado. Total procesados: {len(archivos_pdf)}")