# Landfinder Desktop

Cliente Flutter Windows para el backend local `landfinder`.

## Arranque

La app intenta conectarse a `http://127.0.0.1:8765`. Si el backend no esta
activo, inicia:

```powershell
..\python_engine\.venv\Scripts\python.exe -m landfinder --port 8765 --data-dir ..\data
```

## Vistas MVP

- Dashboard
- Busqueda
- Resultados
- Mapa local de coordenadas
- Fuentes
- Exportar
- Configuracion

## Validacion

```powershell
C:\flutter\bin\flutter.bat --no-version-check --suppress-analytics pub get
C:\flutter\bin\flutter.bat --no-version-check --suppress-analytics analyze
C:\flutter\bin\flutter.bat --no-version-check --suppress-analytics test
C:\flutter\bin\flutter.bat --no-version-check --suppress-analytics build windows --debug
```

El ejecutable debug queda en:

```text
build\windows\x64\runner\Debug\landfinder_desktop.exe
```
