from datetime import date
import xml.etree.ElementTree as ET
import os

def buscar_datos(lista: list, tipo: str) -> str:
    """Busca un dato en el resultado del OCR"""
    if not lista:
        return ""
    try:
        for diccionario in lista:
            if 'properties' in diccionario:
                for propiedades in diccionario['properties']:
                    if propiedades.get('type') == tipo:
                        return propiedades.get('mentionText', "")
    except Exception as e:
        print(f"Error en buscar_datos: {e}")
    return ""

def generar_xml(datos, paginas, ruta, nombre_documento, firmado) -> str:
    """
    Genera XML con los 7 campos requeridos
    """
    try:
        # Crear raíz del XML
        raiz = ET.Element("data")
        
        # Obtener los datos del OCR
        tipo_doc_text = buscar_datos(datos, 'tipo_folio')
        rut_emisor_text = buscar_datos(datos, 'rut_emp')
        rut_destino_text = buscar_datos(datos, 'rut_dest')
        folio_text = buscar_datos(datos, 'id_folio')
        orden_compra_text = buscar_datos(datos, 'orden_compra_detalle')
        total_text = buscar_datos(datos, 'valor_total')
        fecha_doc_text = buscar_datos(datos, 'fecha_emision_folio')
        
        # Limpiar total (quitar puntos)
        if total_text:
            total_text = total_text.replace(".", "")
        
        # Usar nombre_documento como folio si no se encontró
        if not folio_text:
            folio_text = nombre_documento
        
        # Crear elementos del XML
        tipo_doc = ET.SubElement(raiz, "tipo_doc")
        tipo_doc.text = tipo_doc_text if tipo_doc_text else "FACTURA"
        
        rut_emisor = ET.SubElement(raiz, "rut_emisor")
        rut_emisor.text = rut_emisor_text if rut_emisor_text else ""
        
        rut_destino = ET.SubElement(raiz, "rut_destino")
        rut_destino.text = rut_destino_text if rut_destino_text else ""
        
        folio_elem = ET.SubElement(raiz, "folio")
        folio_elem.text = folio_text
        
        orden_compra = ET.SubElement(raiz, "orden_compra")
        orden_compra.text = orden_compra_text if orden_compra_text else ""
        
        total_elem = ET.SubElement(raiz, "total")
        total_elem.text = total_text if total_text else ""
        
        fecha_doc = ET.SubElement(raiz, "fecha_doc")
        fecha_doc.text = fecha_doc_text if fecha_doc_text else ""
        
        # Asegurar que la carpeta existe
        os.makedirs(ruta, exist_ok=True)
        
        # Guardar el XML
        ruta_completa = os.path.join(ruta, f"{nombre_documento}.xml")
        arbol = ET.ElementTree(raiz)
        arbol.write(ruta_completa, encoding="utf-8", xml_declaration=True)
        
        print(f"✅ XML generado: {ruta_completa}")
        
        # Datos para el retorno
        rut_receptor = rut_destino_text if rut_destino_text else "RUT DESCONOCIDO"
        
        fecha_emision = fecha_doc_text
        if not fecha_emision:
            fecha = date.today()
            fecha_emision = f'{fecha.day}/{fecha.month}/{fecha.year}'
        
        tipo_folio_valor = tipo_doc_text if tipo_doc_text else "FACTURA"
        
        # Retorno
        registros_resultado = f'{tipo_folio_valor}|{fecha_emision}|{nombre_documento}.xml|{ruta_completa}|{rut_receptor}'
        return registros_resultado
        
    except Exception as e:
        print(f"❌ Error generando XML: {e}")
        # Devolver un XML de respaldo
        try:
            raiz = ET.Element("data")
            ET.SubElement(raiz, "tipo_doc").text = "ERROR"
            ET.SubElement(raiz, "rut_emisor").text = ""
            ET.SubElement(raiz, "rut_destino").text = ""
            ET.SubElement(raiz, "folio").text = nombre_documento
            ET.SubElement(raiz, "orden_compra").text = ""
            ET.SubElement(raiz, "total").text = ""
            ET.SubElement(raiz, "fecha_doc").text = ""
            
            os.makedirs(ruta, exist_ok=True)
            ruta_completa = os.path.join(ruta, f"{nombre_documento}.xml")
            ET.ElementTree(raiz).write(ruta_completa, encoding="utf-8", xml_declaration=True)
            
            return f'ERROR|{date.today()}|{nombre_documento}.xml|{ruta_completa}|RUT_ERROR'
        except:
            return f'ERROR|{date.today()}|{nombre_documento}.xml|{ruta}|RUT_ERROR'