# puntoticket-alert

Monitor local para revisar eventos de PuntoTicket y avisar cuando cambia la disponibilidad de entradas.

El programa puede usarse con una interfaz sencilla o por consola. Funciona en Windows, macOS y Linux usando solo Python y herramientas del sistema. Por defecto no abre el navegador cuando detecta una alerta; solo lo hace si marcas la opcion en la interfaz o si ejecutas el script con `--open-on-alert`.

## Requisitos

- Python 3 instalado
- Tkinter para usar la interfaz grafica

No requiere instalar paquetes de Python externos.

## Uso con interfaz

En Windows, haz doble clic en:

```text
run_alerta_wwe.bat
```

En macOS o Linux:

```bash
chmod +x run_alerta.sh
./run_alerta.sh
```

Luego:

1. Elige el evento.
2. Ajusta el intervalo de revision.
3. Presiona `Iniciar monitoreo`.

La interfaz muestra la ultima revision, la proxima revision con cuenta regresiva y el historial de cambios.

## Uso por consola

Windows:

```powershell
py ticket_alert.py --once
```

```powershell
py ticket_alert.py --interval 60
```

```powershell
py ticket_alert.py --interval 60 --open-on-alert
```

macOS o Linux:

```bash
python3 ticket_alert.py --once
```

```bash
python3 ticket_alert.py --interval 60
```

```bash
python3 ticket_alert.py --interval 60 --open-on-alert
```

## Alertas por plataforma

- Windows: sonido con `winsound` y notificacion del sistema.
- macOS: sonido y notificacion con `osascript`.
- Linux: campana de terminal y notificacion con `notify-send` si esta disponible.

Los errores temporales de conexion, como timeout o una pagina que no responde, se registran en el historial pero no disparan sonido. El monitor conserva la ultima revision buena para evitar falsas alarmas.

## Archivos generados al ejecutar

Estos archivos no se deben subir al repo:

- `wwe_ticket_state.json`
- `wwe_ticket_alert.log`
- `__pycache__/`

El archivo `wwe_ticket_state.json` guarda la ultima linea base detectada. Si quieres reiniciar la deteccion desde cero, cierra el monitor y borra ese archivo.
