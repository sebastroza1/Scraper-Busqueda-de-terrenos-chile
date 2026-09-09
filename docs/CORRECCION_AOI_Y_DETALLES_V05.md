# Corrección V0.5 - Área exacta y datos puntuales

La prueba visual de v0.4.1 confirmó que el mapa funcionaba, pero reveló dos
problemas de diseño:

1. Una consulta por `bbox` trae objetos que intersectan el rectángulo de
   búsqueda. Una línea/polígono puede continuar muchos kilómetros fuera del
   radio y Folium dibujaba la geometría completa.
2. Las capas WMS eran visuales y por eso no tenían un conteo vectorial; además
   la tabla no mostraba los atributos de cada coincidencia.

## Solución

### AOI circular exacto
- La API sigue recibiendo un bbox pequeño para no descargar datos innecesarios.
- Localmente se crea un círculo métrico exacto usando una proyección AEQD
  centrada en el terreno.
- Cada geometría se filtra por intersección real.
- La geometría visible se recorta al círculo antes de dibujarla.
- Por eso ya no deberían aparecer ríos/carreteras/polígonos extendiéndose por
  todo Chile fuera del área analizada.

### Datos puntuales
Cada coincidencia ahora incluye:
- fuente;
- nombre/etiqueta inferida;
- distancia mínima al punto;
- hasta seis atributos principales en tabla;
- popup con hasta doce atributos al hacer clic.

### WMS
Para GeoServer, el sistema intenta automáticamente cambiar `/wms` por `/wfs`.
Si funciona, la capa pasa a vectorial y puede:
- contarse;
- filtrarse;
- recortarse;
- mostrar atributos.

Si no existe WFS, el estado es `VISUAL_ONLY` y el conteo aparece como `N/D`,
no como cero.

### Estados
- `OK`: fuente respondió y hay coincidencias.
- `OK_SIN_COINCIDENCIAS`: fuente respondió correctamente, pero no hay objetos
  dentro del área seleccionada.
- `VISUAL_ONLY`: se puede renderizar, pero no hay servicio vectorial validado.
- `SOURCE_ERROR`: la consulta falló.
