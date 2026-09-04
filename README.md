# puntoticket-alert

Monitor local para revisar eventos de PuntoTicket y avisar cuando cambia la disponibilidad de entradas.

El programa puede usarse con una interfaz sencilla o por consola. Por defecto no abre el navegador cuando detecta una alerta; solo lo hace si marcas la opcion en la interfaz o si ejecutas el script con `--open-on-alert`.

## Requisitos

- Windows
- Python 3 instalado

No requiere instalar paquetes externos.

## Uso con interfaz

Haz doble clic en:

```text
run_alerta_wwe.bat
```

Luego:

1. Elige el evento.
2. Ajusta el intervalo de revision.
3. Presiona `Iniciar monitoreo`.

La interfaz muestra la ultima revision, la proxima revision con cuenta regresiva y el historial de cambios.

## Uso por consola

Revisar una sola vez:

```powershell
py ticket_alert.py --once
```

Revisar cada 60 segundos:

```powershell
py ticket_alert.py --interval 60
```

Abrir navegador automaticamente cuando haya alerta:

```powershell
py ticket_alert.py --interval 60 --open-on-alert
```

## Archivos generados al ejecutar

Estos archivos no se deben subir al repo:

- `wwe_ticket_state.json`
- `wwe_ticket_alert.log`
- `__pycache__/`

El archivo `wwe_ticket_state.json` guarda la ultima linea base detectada. Si quieres reiniciar la deteccion desde cero, cierra el monitor y borra ese archivo.
