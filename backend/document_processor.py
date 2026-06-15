# document_processor.py
import os
import tempfile
import re
from PIL import Image, ImageEnhance
import pytesseract
from docx import Document
import docx2txt
import fitz
import subprocess
import platform

class DocumentProcessor:
    """Procesa diferentes tipos de documentos: PDF, Word, Imágenes"""
    
    @staticmethod
    def extraer_texto_pdf(ruta_pdf: str) -> str:
        """Extrae texto de PDF usando PyMuPDF con mejor manejo de OCR"""
        texto_completo = ""
        try:
            doc = fitz.open(ruta_pdf)
            for num_pagina, pagina in enumerate(doc, 1):
                # Intentar extraer texto normal
                texto = pagina.get_text()
                if texto.strip():
                    texto_completo += f"\n--- PÁGINA {num_pagina} ---\n" + texto + "\n"
                else:
                    # Si no hay texto, aplicar OCR con mejor resolución
                    print(f"   📄 Página {num_pagina} sin texto. Aplicando OCR...")
                    # Aumentar resolución para mejor OCR
                    zoom = 2
                    matriz = fitz.Matrix(zoom, zoom)
                    pix = pagina.get_pixmap(matrix=matriz)
                    img_path = tempfile.NamedTemporaryFile(suffix='.png', delete=False).name
                    pix.save(img_path)
                    texto_ocr = DocumentProcessor.extraer_texto_imagen(img_path)
                    os.unlink(img_path)
                    if texto_ocr:
                        texto_completo += f"\n--- PÁGINA {num_pagina} (OCR) ---\n" + texto_ocr + "\n"
            doc.close()
            return texto_completo.strip()
        except Exception as e:
            print(f"Error extrayendo texto PDF: {e}")
            return ""
    
    @staticmethod
    def extraer_texto_imagen(ruta_imagen: str, idioma: str = 'spa+eng') -> str:
        """Extrae texto de imágenes usando Tesseract OCR mejorado"""
        try:
            # Abrir imagen
            imagen = Image.open(ruta_imagen)
            
            # Redimensionar si es muy grande
            max_size = 3000
            if max(imagen.size) > max_size:
                ratio = max_size / max(imagen.size)
                nuevo_tamano = (int(imagen.size[0] * ratio), int(imagen.size[1] * ratio))
                imagen = imagen.resize(nuevo_tamano, Image.Resampling.LANCZOS)
            
            # Convertir a escala de grises
            imagen_gris = imagen.convert('L')
            
            # Mejorar contraste
            enhancer = ImageEnhance.Contrast(imagen_gris)
            imagen_mejorada = enhancer.enhance(2)
            
            # Binarización adaptativa
            umbral = 150
            imagen_binaria = imagen_mejorada.point(lambda p: 255 if p > umbral else 0)
            
            # Configuración de Tesseract mejorada
            config = '--psm 6 --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.-/:,'
            
            texto = pytesseract.image_to_string(
                imagen_binaria, 
                lang=idioma,
                config=config
            )
            
            return texto.strip()
        except Exception as e:
            print(f"Error extrayendo texto imagen: {e}")
            return ""
    
    @staticmethod
    def extraer_datos_permiso(texto: str) -> dict:
        """Extrae datos específicos de un Permiso de Trabajo General usando regex"""
        datos = {
            'numero_permiso': '',
            'fecha_inicio': '',
            'hora_inicio': '',
            'fecha_termino': '',
            'hora_termino': '',
            'responsable_nombre': '',
            'empresa_contratista': '',
            'supervisor_contratista': '',
            'conformidad': '',
            'fecha_cierre': '',
            'hora_cierre': ''
        }
        
        # Buscar número de permiso
        patrones_numero = [
            r'[Nn]úmero\s*[Dd]e\s*[Pp]ermiso\s*:?\s*([A-Z0-9\-]+)',
            r'[Pp]ermiso\s*[Nn][°º]\s*:?\s*([A-Z0-9\-]+)',
            r'PT[-\s]*([A-Z0-9\-]+)',
            r'ID[:\s]*([A-Z0-9\-]+)'
        ]
        for patron in patrones_numero:
            match = re.search(patron, texto)
            if match:
                datos['numero_permiso'] = match.group(1).strip()
                break
        
        # Buscar fechas
        patron_fecha = r'(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})'
        fechas = re.findall(patron_fecha, texto)
        if len(fechas) >= 1:
            datos['fecha_inicio'] = fechas[0]
        if len(fechas) >= 2:
            datos['fecha_termino'] = fechas[1]
        if len(fechas) >= 3:
            datos['fecha_cierre'] = fechas[2]
        
        # Buscar horas
        patron_hora = r'(\d{1,2}:\d{2})'
        horas = re.findall(patron_hora, texto)
        if len(horas) >= 1:
            datos['hora_inicio'] = horas[0]
        if len(horas) >= 2:
            datos['hora_termino'] = horas[1]
        if len(horas) >= 3:
            datos['hora_cierre'] = horas[2]
        
        # Buscar responsable
        patrones_responsable = [
            r'[Rr]esponsable\s*:?\s*([^\n]+)',
            r'[Nn]ombre\s*[Rr]esponsable\s*:?\s*([^\n]+)'
        ]
        for patron in patrones_responsable:
            match = re.search(patron, texto)
            if match:
                datos['responsable_nombre'] = match.group(1).strip()[:50]
                break
        
        # Buscar empresa contratista
        patrones_empresa = [
            r'[Ee]mpresa\s*[Cc]ontratista\s*:?\s*([^\n]+)',
            r'[Cc]ontratista\s*:?\s*([^\n]+)'
        ]
        for patron in patrones_empresa:
            match = re.search(patron, texto)
            if match:
                datos['empresa_contratista'] = match.group(1).strip()[:50]
                break
        
        # Buscar supervisor
        patrones_supervisor = [
            r'[Ss]upervisor\s*:?\s*([^\n]+)',
            r'[Ss]upervisor\s*[Dd]el\s*[Cc]ontratista\s*:?\s*([^\n]+)'
        ]
        for patron in patrones_supervisor:
            match = re.search(patron, texto)
            if match:
                datos['supervisor_contratista'] = match.group(1).strip()[:50]
                break
        
        # Buscar conformidad
        if re.search(r'[Cc]onforme', texto):
            datos['conformidad'] = 'Conforme'
        elif re.search(r'[Nn]o\s*[Cc]onforme', texto):
            datos['conformidad'] = 'No conforme'
        
        return datos
    
    @staticmethod
    def extraer_datos_gasto(texto: str) -> dict:
        """Extrae datos de Formulario de Gastos Menores"""
        datos = {
            'folio': '',
            'fecha': '',
            'rut_solicitante': '',
            'nombre_solicitante': '',
            'monto_total': '',
            'descripcion': '',
            'centro_costo': '',
            'aprobador': ''
        }
        
        # Buscar folio
        patrones_folio = [
            r'[Ff]ormulario\s*[Nn][°º]\s*:?\s*([A-Z0-9\-]+)',
            r'[Ff]olio\s*:?\s*([A-Z0-9\-]+)'
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
        
        # Buscar RUT
        patron_rut = r'[Rr]ut\s*:?\s*(\d{1,2}\.\d{3}\.\d{3}[-][\dkK])'
        match = re.search(patron_rut, texto)
        if match:
            datos['rut_solicitante'] = match.group(1)
        
        # Buscar monto
        patron_monto = r'[Mm]onto\s*[Tt]otal\s*:?\s*\$?\s*([\d\.,]+)'
        match = re.search(patron_monto, texto)
        if match:
            datos['monto_total'] = match.group(1)
        
        return datos


def configurar_tesseract():
    """Configura Tesseract OCR"""
    sistema = platform.system()
    
    if sistema == "Windows":
        rutas_tesseract = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ]
        for ruta in rutas_tesseract:
            if os.path.exists(ruta):
                pytesseract.pytesseract.tesseract_cmd = ruta
                print(f"✅ Tesseract configurado en: {ruta}")
                return True
    
    try:
        subprocess.run(['tesseract', '--version'], capture_output=True)
        print("✅ Tesseract en PATH")
        return True
    except:
        print("⚠️ Tesseract no encontrado")
        return False