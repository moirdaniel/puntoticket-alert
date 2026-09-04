import argparse
import datetime as dt
import hashlib
import html
import json
import os
import platform
import queue
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
import webbrowser

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:
    tk = None
    ttk = None


# ============================================================
# CONFIGURACION
# ============================================================

URLS_A_REVISAR = [
    "https://www.puntoticket.com/wwe-live-scl",
    "https://www.puntoticket.com/evento/wwe-movistar-arena-sep-2026",
]

EVENTOS_PREDEFINIDOS = {
    "WWE Live Santiago": URLS_A_REVISAR,
    "Evento personalizado": [],
}

BOTONES_PRINCIPALES = [
    {"archivo": "preventa-fans.png", "nombre": "Preventa fans"},
    {"archivo": "btn_tenpo.png", "nombre": "Preventa Tenpo"},
    {"archivo": "compra-normal.png", "nombre": "Venta general"},
]

ESTADOS_CERRADOS = {
    "AGOTADO",
    "PROXIMAMENTE",
    "PRÓXIMAMENTE",
    "NO_ENCONTRADO",
    "SIN_ESTADO",
}


# ============================================================
# UTILIDADES BASICAS
# ============================================================

def fecha_hora_actual():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def calcular_hash(texto):
    return hashlib.sha256(texto.encode("utf-8", errors="ignore")).hexdigest()


def limpiar_html(texto_html):
    """Convierte HTML en texto simple para poder buscar palabras como AGOTADO."""
    texto_html = re.sub(r"<script\b.*?</script>", " ", texto_html, flags=re.I | re.S)
    texto_html = re.sub(r"<style\b.*?</style>", " ", texto_html, flags=re.I | re.S)
    texto_html = re.sub(r"<[^>]+>", " ", texto_html)
    texto_html = html.unescape(texto_html)
    return re.sub(r"\s+", " ", texto_html).strip()


def crear_carpeta_si_falta(ruta_archivo):
    carpeta = os.path.dirname(os.path.abspath(ruta_archivo))
    if carpeta:
        os.makedirs(carpeta, exist_ok=True)


# ============================================================
# DESCARGA DE PAGINA
# ============================================================

def descargar_pagina(url, timeout):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        contenido = response.read()
        content_type = response.headers.get("content-type", "")
        charset = obtener_charset(content_type)
        return contenido.decode(charset, errors="replace")


def obtener_charset(content_type):
    match = re.search(r"charset=([\w-]+)", content_type, re.I)
    if match:
        return match.group(1)
    return "utf-8"


# ============================================================
# ANALISIS DE DISPONIBILIDAD
# ============================================================

def analizar_todas_las_paginas(urls, timeout):
    paginas = []
    errores = []

    for url in urls:
        try:
            html_pagina = descargar_pagina(url, timeout)
            paginas.append(analizar_pagina(url, html_pagina))
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            errores.append({"url": url, "error": str(error)})

    posible_disponibilidad = any(
        pagina["boton_abierto"] or pagina["estado_abierto"]
        for pagina in paginas
    )

    resultado = {
        "checked_at": fecha_hora_actual(),
        "available": posible_disponibilidad,
        "pages": paginas,
        "errors": errores,
    }
    resultado["fingerprint"] = crear_huella_de_resultado(resultado)
    return resultado


def analizar_pagina(url, html_pagina):
    texto = limpiar_html(html_pagina).upper()
    botones = [analizar_boton(html_pagina, boton) for boton in BOTONES_PRINCIPALES]

    return {
        "url": url,
        "agotado_count": texto.count("AGOTADO"),
        "disponible_count": texto.count("DISPONIBLE"),
        "button_states": botones,
        "boton_abierto": hay_boton_con_link_activo(botones),
        "estado_abierto": hay_estado_de_venta(botones),
        "choose_section_hash": calcular_hash(extraer_zona_tickets(html_pagina)),
        "page_hash": calcular_hash(html_pagina),
    }


def analizar_boton(html_pagina, boton_config):
    imagen_boton = boton_config["archivo"]
    posicion_imagen = html_pagina.lower().find(imagen_boton.lower())

    if posicion_imagen < 0:
        return crear_estado_boton(boton_config, False, "", True, "NO_ENCONTRADO")

    bloque_boton = extraer_bloque_cercano(html_pagina, posicion_imagen)
    href = extraer_href(bloque_boton)
    atributos_link = extraer_atributos_del_link(bloque_boton)
    estado = extraer_estado_visible(bloque_boton)
    esta_inactivo = "inactive" in atributos_link.lower()

    return crear_estado_boton(
        boton_config=boton_config,
        presente=True,
        href=href,
        inactivo=esta_inactivo,
        estado=estado or "SIN_ESTADO",
    )


def crear_estado_boton(boton_config, presente, href, inactivo, estado):
    return {
        "name": boton_config["nombre"],
        "image": boton_config["archivo"],
        "present": presente,
        "href": href,
        "inactive": inactivo,
        "state": estado,
    }


def extraer_bloque_cercano(html_pagina, posicion):
    inicio = max(0, html_pagina.rfind("<div", 0, posicion - 1_000))
    fin = html_pagina.find("</div>", posicion)

    if fin < 0:
        return html_pagina[posicion:posicion + 1_000]

    return html_pagina[inicio:fin + len("</div>")]


def extraer_href(bloque_html):
    match = re.search(r"<a\b[^>]*href=[\"']([^\"']*)[\"'][^>]*>", bloque_html, re.I | re.S)
    if not match:
        return ""
    return html.unescape(match.group(1).strip())


def extraer_atributos_del_link(bloque_html):
    match = re.search(r"<a\b([^>]*)>", bloque_html, re.I | re.S)
    if not match:
        return ""
    return match.group(1)


def extraer_estado_visible(bloque_html):
    match = re.search(
        r"<p\b[^>]*class=[\"'][^\"']*state[^\"']*[\"'][^>]*>(.*?)</p>",
        bloque_html,
        re.I | re.S,
    )
    if not match:
        return ""
    return limpiar_html(match.group(1)).upper()


def hay_boton_con_link_activo(botones):
    return any(boton["href"] and not boton["inactive"] for boton in botones)


def hay_estado_de_venta(botones):
    return any(boton["state"] not in ESTADOS_CERRADOS for boton in botones)


def extraer_zona_tickets(html_pagina):
    match = re.search(
        r'id=["\']choose-tickets-section["\'](.*?)(?:section-resena|</main>)',
        html_pagina,
        re.I | re.S,
    )
    if match:
        return match.group(1)
    return html_pagina


def crear_huella_de_resultado(resultado):
    """La huella permite detectar cambios aunque el texto exacto sea grande."""
    datos_importantes = {
        "pages": [
            {
                "url": pagina["url"],
                "agotado_count": pagina["agotado_count"],
                "button_states": pagina["button_states"],
                "boton_abierto": pagina["boton_abierto"],
                "estado_abierto": pagina["estado_abierto"],
                "choose_section_hash": pagina["choose_section_hash"],
            }
            for pagina in resultado["pages"]
        ],
    }

    texto = json.dumps(datos_importantes, sort_keys=True, ensure_ascii=True)
    return calcular_hash(texto)


def obtener_huella_comparable(estado_guardado):
    if not estado_guardado:
        return None

    if "pages" in estado_guardado:
        return crear_huella_de_resultado(estado_guardado)

    return estado_guardado.get("fingerprint")


# ============================================================
# ARCHIVOS DE ESTADO Y LOG
# ============================================================

def cargar_estado(ruta):
    if not os.path.exists(ruta):
        return None

    with open(ruta, "r", encoding="utf-8") as archivo:
        return json.load(archivo)


def guardar_estado(ruta, estado):
    crear_carpeta_si_falta(ruta)
    with open(ruta, "w", encoding="utf-8") as archivo:
        json.dump(estado, archivo, indent=2, ensure_ascii=False)


def agregar_log(ruta, mensaje):
    crear_carpeta_si_falta(ruta)
    with open(ruta, "a", encoding="utf-8") as archivo:
        archivo.write(mensaje + "\n")


# ============================================================
# ALERTAS
# ============================================================

def avisar(titulo, mensaje):
    hacer_sonido()
    mostrar_notificacion(titulo, mensaje)


def hacer_sonido():
    sistema = platform.system().lower()

    if sistema == "windows":
        hacer_sonido_windows()
        return

    if sistema == "darwin":
        hacer_sonido_macos()
        return

    hacer_sonido_linux()


def hacer_sonido_windows():
    try:
        import winsound

        for _ in range(4):
            winsound.Beep(1200, 450)
            time.sleep(0.15)
    except Exception:
        pass


def hacer_sonido_macos():
    ejecutar_silencioso(["osascript", "-e", "beep 4"])


def hacer_sonido_linux():
    print("\a\a\a\a", end="", flush=True)

    if shutil.which("paplay"):
        ejecutar_silencioso(["paplay", "/usr/share/sounds/freedesktop/stereo/complete.oga"])
    elif shutil.which("aplay"):
        ejecutar_silencioso(["aplay", "/usr/share/sounds/alsa/Front_Center.wav"])


def mostrar_notificacion(titulo, mensaje):
    sistema = platform.system().lower()

    if sistema == "windows":
        mostrar_notificacion_windows(titulo, mensaje)
        return

    if sistema == "darwin":
        mostrar_notificacion_macos(titulo, mensaje)
        return

    mostrar_notificacion_linux(titulo, mensaje)


def mostrar_notificacion_windows(titulo, mensaje):
    comando = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$n=New-Object System.Windows.Forms.NotifyIcon; "
        "$n.Icon=[System.Drawing.SystemIcons]::Information; "
        "$n.BalloonTipTitle="
        + json.dumps(titulo)
        + "; $n.BalloonTipText="
        + json.dumps(mensaje)
        + "; $n.Visible=$true; "
        + "$n.ShowBalloonTip(10000); "
        + "Start-Sleep -Seconds 10; "
        + "$n.Dispose()"
    )

    ejecutar_silencioso(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", comando])


def mostrar_notificacion_macos(titulo, mensaje):
    script = f"display notification {json.dumps(mensaje)} with title {json.dumps(titulo)}"
    ejecutar_silencioso(["osascript", "-e", script])


def mostrar_notificacion_linux(titulo, mensaje):
    if shutil.which("notify-send"):
        ejecutar_silencioso(["notify-send", titulo, mensaje])


def ejecutar_silencioso(comando):
    try:
        subprocess.Popen(
            comando,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        pass


# ============================================================
# SALIDA EN PANTALLA
# ============================================================

def imprimir_inicio(urls, intervalo):
    print("")
    print("============================================================")
    print(" Monitor WWE PuntoTicket")
    print("============================================================")
    print(f" Revisando cada {intervalo} segundos")
    print(" Para detenerlo: Ctrl + C")
    print("")
    print(" Paginas revisadas:")
    for url in urls:
        print(f" - {url}")
    print("")


def crear_linea_de_estado(resultado, debe_alertar):
    estado = "ALERTA: revisa PuntoTicket ahora" if debe_alertar else "Sin cambio"
    lineas = [
        "",
        "------------------------------------------------------------",
        f"Revision: {resultado['checked_at']}",
        f"Estado:   {estado}",
        "",
        "Botones principales:",
    ]

    for boton in obtener_botones_unicos(resultado):
        lineas.append(f" - {resumir_boton(boton)}")

    if resultado["errors"]:
        lineas.append("")
        lineas.append("Errores:")
        for error in resultado["errors"]:
            lineas.append(f" - {nombre_corto_url(error['url'])}: {error['error']}")

    lineas.append("")
    lineas.append("Detalle paginas:")
    for pagina in resultado["pages"]:
        lineas.append(
            f" - {nombre_corto_url(pagina['url'])}: "
            f"{pagina['agotado_count']} textos AGOTADO detectados"
        )

    return "\n".join(lineas)


def obtener_botones_unicos(resultado):
    botones_por_nombre = {}

    for pagina in resultado["pages"]:
        for boton in pagina["button_states"]:
            botones_por_nombre[boton["name"]] = boton

    return botones_por_nombre.values()


def resumir_boton(boton):
    estado = boton["state"]
    link = "con link" if boton["href"] else "sin link"
    actividad = "inactivo" if boton["inactive"] else "activo"
    return f"{boton['name']}: {estado} ({link}, {actividad})"


def nombre_corto_url(url):
    if "evento/wwe-movistar-arena" in url:
        return "Pagina evento"
    if "wwe-live-scl" in url:
        return "Landing WWE"
    return url


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def crear_argumentos():
    parser = argparse.ArgumentParser(description="Monitor de entradas WWE en PuntoTicket.")
    parser.add_argument("--interval", type=int, default=60, help="Segundos entre revisiones. Default: 60.")
    parser.add_argument("--timeout", type=int, default=20, help="Timeout HTTP en segundos. Default: 20.")
    parser.add_argument("--state-file", default="wwe_ticket_state.json", help="Archivo donde guarda la linea base.")
    parser.add_argument("--log-file", default="wwe_ticket_alert.log", help="Archivo de log.")
    parser.add_argument("--once", action="store_true", help="Revisar una sola vez y salir.")
    parser.add_argument("--open-on-alert", action="store_true", help="Abrir PuntoTicket cuando detecte cambio.")
    parser.add_argument("--gui", action="store_true", help="Abrir interfaz grafica sencilla.")
    parser.add_argument("--url", action="append", dest="urls", help="URL extra a monitorear.")
    return parser.parse_args()


def ejecutar_revision(args, urls):
    resultado = analizar_todas_las_paginas(urls, args.timeout)
    estado_anterior = cargar_estado(args.state_file)
    hay_errores = bool(resultado["errors"])

    hubo_cambio = (
        not hay_errores
        and estado_anterior is not None
        and obtener_huella_comparable(estado_anterior) != resultado["fingerprint"]
    )
    debe_alertar = resultado["available"] or hubo_cambio

    linea = crear_linea_de_estado(resultado, debe_alertar)
    print(linea, flush=True)
    agregar_log(args.log_file, linea)

    if not hay_errores or resultado["available"]:
        guardar_estado(args.state_file, resultado)

    if debe_alertar:
        avisar_y_abrir_pagina(args.open_on_alert, urls[0])

    return {
        "resultado": resultado,
        "debe_alertar": debe_alertar,
        "linea": linea,
    }


def avisar_y_abrir_pagina(abrir_pagina, url_a_abrir):
    avisar(
        "PuntoTicket WWE",
        "Cambio detectado o posible venta disponible. Revisa la pagina ahora.",
    )

    if abrir_pagina:
        webbrowser.open(url_a_abrir)


# ============================================================
# INTERFAZ GRAFICA
# ============================================================

class MonitorGUI:
    def __init__(self, args):
        self.args = args
        self.worker = None
        self.detener = threading.Event()
        self.mensajes = queue.Queue()

        self.root = tk.Tk()
        self.root.title("Alerta PuntoTicket")
        self.root.geometry("820x620")
        self.root.minsize(720, 520)

        self.evento_var = tk.StringVar(value="WWE Live Santiago")
        self.url_var = tk.StringVar(value=URLS_A_REVISAR[0])
        self.intervalo_var = tk.IntVar(value=args.interval)
        self.abrir_navegador_var = tk.BooleanVar(value=False)
        self.estado_var = tk.StringVar(value="Detenido")
        self.ultima_revision_var = tk.StringVar(value="Ultima revision: pendiente")
        self.proxima_revision_var = tk.StringVar(value="Proxima revision: pendiente")

        self.crear_componentes()
        self.root.after(200, self.procesar_mensajes)
        self.root.protocol("WM_DELETE_WINDOW", self.cerrar)

    def crear_componentes(self):
        contenedor = ttk.Frame(self.root, padding=16)
        contenedor.pack(fill="both", expand=True)

        ttk.Label(contenedor, text="Evento a revisar").grid(row=0, column=0, sticky="w")
        selector = ttk.Combobox(
            contenedor,
            textvariable=self.evento_var,
            values=list(EVENTOS_PREDEFINIDOS.keys()),
            state="readonly",
        )
        selector.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 12))
        selector.bind("<<ComboboxSelected>>", self.actualizar_url_por_evento)

        ttk.Label(contenedor, text="URL personalizada o principal").grid(row=2, column=0, sticky="w")
        ttk.Entry(contenedor, textvariable=self.url_var).grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 12),
        )

        ttk.Label(contenedor, text="Intervalo en segundos").grid(row=4, column=0, sticky="w")
        ttk.Spinbox(
            contenedor,
            from_=15,
            to=600,
            textvariable=self.intervalo_var,
            width=10,
        ).grid(row=5, column=0, sticky="w", pady=(4, 12))

        ttk.Checkbutton(
            contenedor,
            text="Abrir navegador cuando haya alerta",
            variable=self.abrir_navegador_var,
        ).grid(row=5, column=1, sticky="w", pady=(4, 12))

        botones = ttk.Frame(contenedor)
        botones.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(0, 12))

        self.iniciar_btn = ttk.Button(botones, text="Iniciar monitoreo", command=self.iniciar)
        self.iniciar_btn.pack(side="left")

        self.detener_btn = ttk.Button(botones, text="Detener", command=self.detener_monitoreo, state="disabled")
        self.detener_btn.pack(side="left", padx=(8, 0))

        ttk.Button(botones, text="Abrir pagina", command=self.abrir_pagina_actual).pack(side="left", padx=(8, 0))

        ttk.Label(botones, textvariable=self.estado_var).pack(side="left", padx=(16, 0))

        tiempos = ttk.Frame(contenedor)
        tiempos.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        ttk.Label(tiempos, textvariable=self.ultima_revision_var).pack(side="left")
        ttk.Label(tiempos, textvariable=self.proxima_revision_var).pack(side="left", padx=(24, 0))

        ttk.Label(contenedor, text="Historial").grid(row=8, column=0, sticky="w")
        self.salida = tk.Text(contenedor, height=20, wrap="word")
        self.salida.grid(row=9, column=0, columnspan=2, sticky="nsew", pady=(4, 0))

        scroll = ttk.Scrollbar(contenedor, orient="vertical", command=self.salida.yview)
        scroll.grid(row=9, column=2, sticky="ns", pady=(4, 0))
        self.salida.configure(yscrollcommand=scroll.set)

        contenedor.columnconfigure(0, weight=1)
        contenedor.columnconfigure(1, weight=1)
        contenedor.rowconfigure(9, weight=1)

        self.escribir_en_pantalla("Listo. El navegador no se abrira salvo que marques el checkbox.\n")

    def actualizar_url_por_evento(self, _event=None):
        urls = EVENTOS_PREDEFINIDOS.get(self.evento_var.get(), [])
        if urls:
            self.url_var.set(urls[0])
        else:
            self.url_var.set("")

    def obtener_urls_seleccionadas(self):
        evento = self.evento_var.get()
        url_manual = self.url_var.get().strip()

        if evento != "Evento personalizado":
            return EVENTOS_PREDEFINIDOS[evento]

        if not url_manual:
            raise ValueError("Debes pegar una URL para el evento personalizado.")

        return [url_manual]

    def iniciar(self):
        try:
            urls = self.obtener_urls_seleccionadas()
        except ValueError as error:
            self.escribir_en_pantalla(f"\nERROR: {error}\n")
            return

        self.detener.clear()
        self.args.interval = max(15, int(self.intervalo_var.get()))
        self.args.open_on_alert = bool(self.abrir_navegador_var.get())

        self.iniciar_btn.configure(state="disabled")
        self.detener_btn.configure(state="normal")
        self.estado_var.set("Monitoreando")
        self.ultima_revision_var.set("Ultima revision: pendiente")
        self.proxima_revision_var.set("Proxima revision: revisando ahora")

        self.escribir_en_pantalla("\n============================================================\n")
        self.escribir_en_pantalla("Monitor iniciado desde la interfaz\n")
        self.escribir_en_pantalla(f"Evento: {self.evento_var.get()}\n")
        self.escribir_en_pantalla(f"Intervalo: {self.args.interval}s\n")
        self.escribir_en_pantalla(f"Abrir navegador: {'si' if self.args.open_on_alert else 'no'}\n")
        for url in urls:
            self.escribir_en_pantalla(f"- {url}\n")

        self.worker = threading.Thread(
            target=self.loop_monitoreo,
            args=(urls,),
            daemon=True,
        )
        self.worker.start()

    def loop_monitoreo(self, urls):
        while not self.detener.is_set():
            revision = ejecutar_revision(self.args, urls)
            self.mensajes.put({
                "tipo": "revision",
                "texto": revision["linea"] + "\n",
                "fecha": revision["resultado"]["checked_at"],
                "alerta": revision["debe_alertar"],
            })

            espera_total = max(15, self.args.interval)
            for restante in range(espera_total, 0, -1):
                if self.detener.is_set():
                    break
                self.mensajes.put({"tipo": "contador", "restante": restante})
                time.sleep(1)

        self.mensajes.put({"tipo": "detenido"})

    def detener_monitoreo(self):
        self.detener.set()
        self.iniciar_btn.configure(state="normal")
        self.detener_btn.configure(state="disabled")
        self.estado_var.set("Detenido")
        self.proxima_revision_var.set("Proxima revision: detenida")

    def procesar_mensajes(self):
        while True:
            try:
                mensaje = self.mensajes.get_nowait()
            except queue.Empty:
                break
            self.procesar_mensaje(mensaje)

        self.root.after(200, self.procesar_mensajes)

    def procesar_mensaje(self, mensaje):
        if isinstance(mensaje, str):
            self.escribir_en_pantalla(mensaje)
            return

        tipo = mensaje.get("tipo")

        if tipo == "revision":
            self.ultima_revision_var.set(f"Ultima revision: {mensaje['fecha']}")
            self.estado_var.set("ALERTA detectada" if mensaje["alerta"] else "Monitoreando")
            self.escribir_en_pantalla(mensaje["texto"])
            return

        if tipo == "contador":
            self.proxima_revision_var.set(f"Proxima revision: en {mensaje['restante']}s")
            return

        if tipo == "detenido":
            self.estado_var.set("Detenido")
            self.proxima_revision_var.set("Proxima revision: detenida")
            self.escribir_en_pantalla("\nMonitor detenido.\n")

    def escribir_en_pantalla(self, texto):
        self.salida.insert("end", texto)
        self.salida.see("end")

    def abrir_pagina_actual(self):
        try:
            urls = self.obtener_urls_seleccionadas()
        except ValueError as error:
            self.escribir_en_pantalla(f"\nERROR: {error}\n")
            return

        webbrowser.open(urls[0])

    def cerrar(self):
        self.detener.set()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    args = crear_argumentos()
    urls = URLS_A_REVISAR + (args.urls or [])

    if args.gui:
        if tk is None or ttk is None:
            print("ERROR: La interfaz grafica requiere Tkinter.")
            print("Puedes usar el modo consola con: python ticket_alert.py --interval 60")
            return 2
        MonitorGUI(args).run()
        return 0

    imprimir_inicio(urls, args.interval)

    while True:
        revision = ejecutar_revision(args, urls)
        resultado = revision["resultado"]

        if args.once:
            return 0 if not resultado["errors"] else 2

        time.sleep(max(15, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
