#!/usr/bin/python3
# -*- coding: utf-8 -*-

"""
WebSocketd Printer
Copyright (C) SASCO SpA (https://sasco.cl)

Este programa es software libre: usted puede redistribuirlo y/o
modificarlo bajo los términos de la Licencia Pública General GNU
publicada por la Fundación para el Software Libre, ya sea la versión
3 de la Licencia, o (a su elección) cualquier versión posterior de la
misma.

Este programa se distribuye con la esperanza de que sea útil, pero
SIN GARANTÍA ALGUNA; ni siquiera la garantía implícita
MERCANTIL o de APTITUD PARA UN PROPÓSITO DETERMINADO.
Consulte los detalles de la Licencia Pública General GNU para obtener
una información más detallada.

Debería haber recibido una copia de la Licencia Pública General GNU
junto a este programa.
En caso contrario, consulte <http://www.gnu.org/licenses/gpl.html>.
"""

# valores por defecto para la configuración de la impresora
PRINTER_TYPE = 'system'
PRINTER_URI = None
PRINTER_MARGIN = 0 # rango de 0 a 8
PRINTERS_SUPPORTED = {
    'tm-t20iii': {
        'idVendor': 0x04b8,
        'idProduct': 0x0e28,
    }
}
# módulos que se usarán
import sys
import getopt
import os, os.path
import asyncio
import websockets
import functools
import json
import zipfile
import io
import socket
import subprocess
from escpos.connections import getUSBPrinter

if os.name == 'posix':
    try:
        import cups
    except ModuleNotFoundError:
        pass
elif os.name == 'nt' :
    try:
        import win32print
        import win32api
        import pywintypes
        from PyPDF2 import PdfFileReader, PdfFileWriter
    except ModuleNotFoundError:
        pass
from datetime import datetime
from time import sleep


# función que lanza el websocket de manera asíncrona
def run(printer_type = PRINTER_TYPE, printer_uri = PRINTER_URI, printer_margin = PRINTER_MARGIN):
    print('Iniciando WebSocketd Printer con printer_type=' + str(printer_type) + ', printer_uri=' + str(printer_uri) + ' y printer_margin='+ str(printer_margin))
    # ejecutar demoniop
    try :
        server = websockets.serve(
            functools.partial(
                on_message,
                printer_type = printer_type,
                printer_uri = printer_uri,
                printer_margin = printer_margin,
            ),
            'localhost',
            2186
        )
        asyncio.get_event_loop().run_until_complete(server)
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt :
        print()
        return 0
    return 0

# función que se ejecuta cuando el websocket recibe un mensaje
async def on_message(websocket, path, printer_type, printer_uri, printer_margin):
    # verificar las partes pasadas al script
    # al menos se debe pasar una acción que es la que se está realizando
    parts = path.split('/')
    if len(parts) < 2 or parts[1] == '':
        await websocket.send(json.dumps({
            'status': 1,
            'message': 'Falta indicar la acción que se está solicitando realizar'
        }))
    message = await websocket.recv()
    # procesar tarea "print" para impresión
    if parts[1] == 'print':
        # verificar soporte para impresión
        if os.name == 'posix':
            try:
                import cups
            except ModuleNotFoundError:
                await websocket.send(json.dumps({
                    'status': 1,
                    'message': 'Falta instalar módulo de CUPS para Python (pycups)'
                }))
        elif os.name == 'nt' :
            try:
                import win32print
            except ModuleNotFoundError:
                await websocket.send(json.dumps({
                    'status': 1,
                    'message': 'Falta instalar pywin32'
                }))
        # obtener formato de impresión
        try:
            formato = parts[2]
        except IndexError:
            formato = 'escpos'
        # obtener datos del archivo para impresión
        try :
            z = zipfile.ZipFile(io.BytesIO(message))
            datos = z.read(z.infolist()[0])
        except zipfile.BadZipFile as e:
            await websocket.send(json.dumps({
                'status': 1,
                'message': 'No fue posible obtener el archivo para imprimir (' + str(e) + ')'
            }))
        # opciones para impresión con ESCPOS
        if formato == 'escpos':
            # impresora en red
            if printer_type == 'network':
                try :
                    print_network(datos, printer_uri)
                except (ConnectionRefusedError, OSError) as e:
                    await websocket.send(json.dumps({
                        'status': 1,
                        'message': 'No fue posible imprimir en ' + str(printer_uri) + ' (' + str(e) + ')'
                    }))
            # impresora del sistema
            else:
                try :
                    print_system_escpos(datos, printer_uri)
                except (ConnectionRefusedError, OSError, Exception) as e:
                    await websocket.send(json.dumps({
                        'status': 1,
                        'message': 'No fue posible imprimir en ' + str(printer_uri) + ' (' + str(e) + ')' # TODO revisar mensaje con None
                    }))
        # opciones para impresión usando el PDF
        elif formato == 'pdf':
            # impresora en red
            if printer_type == 'network':
                await websocket.send(json.dumps({
                    'status': 1,
                    'message': 'Tipo de impresora ' + str(printer_type) + ' no soportada con formato ' + formato
                }))
            # impresora del sistema
            else:
                try :
                    pdf_file = establecer_margen(datos,printer_margin)
                    print_system(pdf_file, printer_uri)
                except (ConnectionRefusedError, OSError, Exception) as e:
                    if printer_uri is None:
                        printer_uri = 'default'
                    await websocket.send(json.dumps({
                        'status': 1,
                        'message': 'No fue posible imprimir en ' + str(printer_uri) + ' (' + str(e) + ')'
                    }))
        # formato no soportado (ni ESCPOS, ni PDF)
        else:
            await websocket.send(json.dumps({
                'status': 1,
                'message': 'Formato ' + formato + ' no soportado'
            }))
        # log impresión
        log('Se imprimió usando \'' + formato + '\' en la impresora \'' + str(printer_type) + '\'')
    # todo ok

def establecer_margen(datos,margin):
    cmd_dir = os.path.dirname(os.path.realpath(__file__))
    # crear PDF con la información binaria
    pdf_file = cmd_dir + '/documento.pdf'
    with open(pdf_file, 'wb') as m:
        m.write(datos)
    if margin > 0:
        # leer pdf creado con la informacion binaria
        with open(pdf_file, 'rb') as f:
            p = PdfFileReader(f)
            info = p.getDocumentInfo()
            number_of_pages = p.getNumPages()

            writer = PdfFileWriter()
            # recorrer el pdf creado para establecer el margen
            for i in range(number_of_pages):
                page = p.getPage(i)
                new_page = writer.addBlankPage(
                    page.mediaBox.getWidth(),
                    page.mediaBox.getHeight()
                )
                new_page.mergeScaledTranslatedPage(page, 1, 8, 0)
            new_pdf = cmd_dir + '/documento_margin.pdf'
            # crear el nuevo pdf con el margen
            with open(new_pdf, 'wb') as n:
                writer.write(n)
        try:
            #Eliminar archivo temporal generado
            sleep(6)
            os.remove(pdf_file)
        except OSError as e:
            raise Exception('Error al eliminar archivo temporal de la impresión.')
        return new_pdf
    return pdf_file

# función que realiza la impresión en una impresora de red
def print_network(data, uri):
    if uri.find(':') > 0 :
        host, port = uri.split(':')
        port = int(port)
    else :
        host = uri
        port = 9100
    printer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    printer_socket.connect((host, port))
    printer_socket.send(data)
    printer_socket.shutdown(0)
    printer_socket.close()

# función que realiza la impresión en una impresora de red
def print_system(data, printer = None):
    if printer == None :
        printer = printer_system_get_default()
    if printer == None :
        raise Exception('No fue posible obtener una impresora por defecto.')
    if os.name == 'posix':
        return print_system_linux(data, printer)
    elif os.name == 'nt' :
        return print_system_windows(data, printer)
    else :
        raise Exception('Sistema operativo no soportado.')

# función para imprimir en una impresora tipo system con formato ESCPOS
def print_system_escpos(data, printer_uri= None):
    # verificar que printer uri no sea NONE
    if printer_uri is not None:
        # verificar si es nombre o product/vendor id
        if printer_uri.find(":") == -1:
            # si es nombre
            # realizar un lower a la string
            printer_name = printer_uri.lower()
            # buscar en el diccionario
            printer = None
            # si existe asignar a variable
            if printer_name in PRINTERS_SUPPORTED:
                printer = PRINTERS_SUPPORTED[printer_name]
            # sino existe, mostrar mensaje de impresora no soportada
            else:
                raise Exception('Impresora ' + str(printer_uri) + ' no soportada')
        else:
            try:
                # si es product/vendor id
                idVendor, idProduct = printer_uri.split(":")
                # asignar a variable
                printer = {
                    'idVendor': int(idVendor, 16),
                    'idProduct': int(idProduct, 16),
                }
            except (Exception) as e:
                raise Exception('Formato ingresado no es válido, debe seguir la siguiente estructura idVendor:idProducto')
        printer = getUSBPrinter()(
                idVendor = printer['idVendor'],
                idProduct = printer['idProduct'],
                inputEndPoint = 0x82,
                outputEndPoint = 0x01
            )
        printer.text(data)
        printer.lf()
        return 0
    raise Exception('Debe espeficar el modelo de la impresora o la id del productor y vendor (vendorId:productId) ') #TODO actualizar mensaje

# entrega la impresora por defecto del sistema
def printer_system_get_default() :
    if os.name == 'posix':
        conn = cups.Connection()
        defaultPrinter = conn.getDefault()
        if defaultPrinter is None :
            printers = conn.getPrinters()
            for printer in printers :
                defaultPrinter = printer
                break
    elif os.name == 'nt' :
        defaultPrinter = win32print.GetDefaultPrinter() # función que entrega un string con el nombre de la impresora
    else :
        defaultPrinter = None
    return defaultPrinter

# imprimir en linux
def print_system_linux(pdf, impresora) :
    conn = cups.Connection()
    conn.printFile(impresora, pdf, 'DTE', {})
    return 0

# imprimir en windows
def print_system_windows(pdf, impresora, delay = 5) :
    ImpresoraPorDefecto = str(win32print.GetDefaultPrinter()) # primero guardamos la impresora por defecto
    win32print.SetDefaultPrinter(impresora) # luego se cambia la impresora por defecto por la impresora específica
    try:
        win32api.ShellExecute(0, 'print', pdf, None, '.', 0)
    except pywintypes.error as e:
        print(e.strerror)
        return 1
    sleep(delay) # se espera un tiempo para que se envíe el archivo a la impresora
    win32print.SetDefaultPrinter(ImpresoraPorDefecto) # vuelve a estar la impresora por defecto original
    return 0

# función para log en el servidor de websockets
def log(msg) :
    dt = datetime.now()
    print(str(dt).split('.')[0] + ': ' + msg)

# función de ayuda para el programa
def usage(message = None):
    print("\n" + 'WebSocketd Printer by SASCO SpA', end="\n\n")
    if message is not None:
        print('[error] ' + message, end="\n\n")
    print('Modo de uso:')
    print('  $ '+os.path.basename(sys.argv[0])+' [--printer_type=TYPE] [--printer_uri=URI]', end="\n\n")
    print('  TYPE    :  - usar "system" para una impresora instalada en el equipo. Usado con formato PDF.')
    print('             - usar "network" para una impresora en red. Usado con formato ESCPOS.')
    print('  URI     :  - si TYPE es "system" se puede indicar el nombre de la impresora a usar')
    print('             - si TYPE es "network" es la dirección de la impresora en red. Ejemplo: 172.16.1.5:9100')
    print('  MARGIN  :  - si MARGIN es enviado, se agregará un margen al lado izquierdo de la boleta', end="\n\n")
    if message is None:
        return 0
    else:
        return 1

# función principal a ejecutar en este programa
def main():
    # configuración inicialmente desde variables de entorno
    printer_type = os.getenv('WEBSOCKETD_PRINTER_TYPE', PRINTER_TYPE)
    printer_uri = os.getenv('WEBSOCKETD_PRINTER_URI', PRINTER_URI)
    printer_margin = os.getenv('WEBSOCKETD_PRINTER_MAGIN', PRINTER_MARGIN)
    # configuración desde parámetros pasados al programa
    options = 'h'
    long_options = ['printer_type=', 'printer_uri=', 'printer_margin']
    try:
        opts, args = getopt.getopt(sys.argv[1:], options, long_options)
    except getopt.GetoptError:
        return usage('Ocurrió un error al obtener los parámetros del programa')
    for var, val in opts:
        if var == '--printer_type':
            printer_type = val
        elif var == '--printer_uri':
            if val == 'None':
                val = None
            printer_uri = val
        elif var == '--printer_margin':
            printer_margin = 8
        elif var == '-h':
            return usage()
    # ejecutar websocket con las opciones indicadas
    return run(printer_type, printer_uri, printer_margin)

# ejecutar el programa principal si se llama directamente a este archivo
if __name__ == '__main__':
    sys.exit(main())
