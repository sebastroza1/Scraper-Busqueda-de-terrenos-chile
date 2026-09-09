# Prueba de resistencia 14 días - Windows

La aplicación trae `monitor_once.py`, que ejecuta todas las fuentes P0 y P1
una vez y guarda el resultado en SQLite.

## Probar manualmente

```powershell
.\.venv\Scripts\Activate.ps1
python monitor_once.py
```

## Programador de tareas de Windows

1. Abre **Programador de tareas**.
2. Crea una tarea básica.
3. Desencadenador: diariamente.
4. En configuración avanzada, repetir cada **1 hora** durante **1 día**.
5. Marcar repetir indefinidamente o crear duración de 14 días.
6. Acción: iniciar programa.
7. Programa:
   `RUTA_DEL_PROYECTO\.venv\Scripts\python.exe`
8. Argumentos:
   `monitor_once.py`
9. Iniciar en:
   `RUTA_DEL_PROYECTO`

Después de 14 días, abre la pestaña **Historial** del Source Lab.

## Qué revisar

- porcentaje de OK por fuente;
- errores consecutivos;
- p95 de latencia;
- cambios de `schema_hash`;
- recursos/capas desaparecidos;
- endpoints que pasan de OK a DEGRADED;
- antigüedad y licencia.

No conviertas automáticamente una fuente a ACTIVE solo por tener 99% de
uptime: debe pasar también el gate legal y de calidad.
