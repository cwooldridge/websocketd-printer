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
    except ModuleNotFoundError:
        pass
from datetime import datetime
from time import sleep

# función que lanza el websocket de manera asíncrona
def run(printer_type = PRINTER_TYPE, printer_uri = PRINTER_URI):
    print('Iniciando WebSocketd Printer con printer_type=' + str(printer_type) + ' y printer_uri=' + str(printer_uri))
    # ejecutar demoniop
    try :
        server = websockets.serve(
            functools.partial(
                on_message,
                printer_type = printer_type,
                printer_uri = printer_uri,
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
@asyncio.coroutine
def on_message(websocket, path, printer_type, printer_uri):
    # verificar las partes pasadas al script
    # al menos se debe pasar una acción que es la que se está realizando
    parts = path.split('/')
    if len(parts) < 2 or parts[1] == '':
        yield from websocket.send(json.dumps({
            'status': 1,
            'message': 'Falta indicar la acción que se está solicitando realizar'
        }))
        return 1
    message = yield from websocket.recv()
    # procesar tarea "print" para impresión
    if parts[1] == 'print':
        # verificar soporte para impresión
        if os.name == 'posix':
            try:
                import cups
            except ModuleNotFoundError:
                yield from websocket.send(json.dumps({
                    'status': 1,
                    'message': 'Falta instalar módulo de CUPS para Python (pycups)'
                }))
        elif os.name == 'nt' :
            try:
                import win32print
            except ModuleNotFoundError:
                yield from websocket.send(json.dumps({
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
            yield from websocket.send(json.dumps({
                'status': 1,
                'message': 'No fue posible obtener el archivo para imprimir (' + str(e) + ')'
            }))
            return 1
        # opciones para impresión con ESCPOS
        if formato == 'escpos':
            # impresora en red
            if printer_type == 'network':
                try :
                    print_network(datos, printer_uri)
                except (ConnectionRefusedError, OSError) as e:
                    yield from websocket.send(json.dumps({
                        'status': 1,
                        'message': 'No fue posible imprimir en ' + printer_uri + ' (' + str(e) + ')'
                    }))
                    return 1
            # impresora del sistema
            else:
                yield from websocket.send(json.dumps({
                    'status': 1,
                    'message': 'Tipo de impresora ' + printer_type + ' no soportada con formato ' + formato
                }))
                return 1
        # opciones para impresión usando el PDF
        elif formato == 'pdf':
            # impresora en red
            if printer_type == 'network':
                yield from websocket.send(json.dumps({
                    'status': 1,
                    'message': 'Tipo de impresora ' + printer_type + ' no soportada con formato ' + formato
                }))
                return 1
            # impresora del sistema
            else:
                try :
                    cmd_dir = os.path.dirname(os.path.realpath(__file__))
                    # crear archivo temporal con el PDF
                    dt = datetime.now()
                    ms = (dt.day * 24 * 60 * 60 + dt.second) * 1000 + dt.microsecond / 1000.0
                    pdf_file = cmd_dir + '/documento_' + str(ms) + '.pdf'
                    with open(pdf_file, 'wb') as f:
                        f.write(datos)
                    print_system(pdf_file, printer_uri)
                    try:
                        #Eliminar archivo y directorio temporal generado
                        sleep(6)
                        os.remove(pdf_file)
                    except OSError as e:
                        raise Exception('Error al eliminar archivo temporal de la impresión.')
                except (ConnectionRefusedError, OSError, Exception) as e:
                    if printer_uri is None:
                        printer_uri = 'default'
                    yield from websocket.send(json.dumps({
                        'status': 1,
                        'message': 'No fue posible imprimir en ' + printer_uri + ' (' + str(e) + ')'
                    }))
                    return 1
        # formato no soportado (ni ESCPOS, ni PDF)
        else:
            yield from websocket.send(json.dumps({
                'status': 1,
                'message': 'Formato ' + formato + ' no soportado'
            }))
            return 1
        # log impresión
        log('Se imprimió usando \'' + formato + '\' en la impresora \'' + printer_type + '\'')
    # todo ok
    return 0

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
        raise Exception('No fue posible obtener una impresora por defecto')
    if os.name == 'posix':
        return print_system_linux(data, printer)
    elif os.name == 'nt' :
        return print_system_windows(data, printer)
    else :
        raise Exception('Sistema operativo no soportado')

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
    print('  TYPE :  - usar "system" para una impresora instalada en el equipo. Usado con formato PDF.')
    print('          - usar "network" para una impresora en red. Usado con formato ESCPOS.')
    print('  URI  :  - si TYPE es "system" se puede indicar el nombre de la impresora a usar')
    print('          - si TYPE es "network" es la dirección de la impresora en red. Ejemplo: 172.16.1.5:9100', end="\n\n")
    if message is None:
        return 0
    else:
        return 1

# función principal a ejecutar en este programa
def main():
    # configuración inicialmente desde variables de entorno
    printer_type = os.getenv('WEBSOCKETD_PRINTER_TYPE', PRINTER_TYPE)
    printer_uri = os.getenv('WEBSOCKETD_PRINTER_URI', PRINTER_URI)
    # configuración desde parámetros pasados al programa
    options = 'h'
    long_options = ['printer_type=', 'printer_uri=']
    try:
        opts, args = getopt.getopt(sys.argv[1:], options, long_options)
    except getopt.GetoptError:
        return usage('Ocurrió un error al obtener los parámetros del programa')
    for var, val in opts:
        if var == '--printer_type':
            printer_type = val
        elif var == '--printer_uri':
            printer_uri = val
        elif var == '-h':
            return usage()
    # ejecutar websocket con las opciones indicadas
    return run(printer_type, printer_uri)

# ejecutar el programa principal si se llama directamente a este archivo
if __name__ == '__main__':
    sys.exit(main())
