import os
import json
import base64
#import pyodbc
from io import BytesIO
from PIL import Image, ImageDraw
from werkzeug.utils import secure_filename

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from datetime import datetime
from datetime import time as dt_time

carpeta_documentos = "documentos_procesados"






# Carga de documentos
# OK
def cargar_documento(archivo) -> (tuple[str, str, str] | tuple[None, None, None]):
    """
    Función para cargar el documento por via flask

    Parámetros:
    archivo (any): Archivo a cargar

    Retorna:
    tuple: [ruta del nuevo archivo, nueva carpeta del archivo, nombre del nuevo archivo]
    """

    if hasattr(archivo, 'filename'):
        nombre_archivo = archivo.filename
    else:
        nombre_archivo = archivo.name

    if archivo and documentos_permitidos(nombre_archivo):
        nombre_archivo_seguro = secure_filename(nombre_archivo)

        if not os.path.exists(carpeta_documentos):
            os.makedirs(carpeta_documentos)

        nueva_carpeta = os.path.join(carpeta_documentos, os.path.splitext(nombre_archivo_seguro)[0])
        os.makedirs(nueva_carpeta, exist_ok=True)
        
        nombre_archivo = os.path.splitext(nombre_archivo_seguro)[0]
        ruta_archivo = os.path.join(nueva_carpeta, nombre_archivo_seguro)
        archivo.save(ruta_archivo)

        return (ruta_archivo, nueva_carpeta, nombre_archivo)
    else:
        return (None, None, None)


   

# Obtención de documentos
# OK
def obtener_documentos_procesados() -> list:
    """
    Función que obtiene los documentos

    Retorna:
    list: Listado de documentos procesados
    """

    carpeta = os.path.join(os.getcwd(), "jsons")
    archivos_json = [archivo for archivo in os.listdir(carpeta) if archivo.endswith('.json')]

    resultados = []

    for archivo_json in archivos_json:
        ruta_completa = os.path.join(carpeta, archivo_json)

        with open(ruta_completa, 'r', encoding='utf-8') as f:
            contenido_json = json.load(f)

        resultados.append({"nombre": contenido_json["nombre"], 
                           "archivo": contenido_json["entities"], 
                           "documento": contenido_json["image"], 
                           "numero_pagina": contenido_json['numero_pagina'], 
                           "firmado": contenido_json['firmado']})
        
    return resultados

# OK


