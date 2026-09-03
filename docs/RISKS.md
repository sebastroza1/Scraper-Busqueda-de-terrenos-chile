# Riesgos Tecnicos Y Legales

## Riesgos tecnicos

- Fuentes privadas pueden cambiar HTML, bloquear automatizacion o no permitir
  scraping en sus terminos.
- APIs oficiales pueden exigir ticket, OAuth, Clave Unica o limites diarios.
- Datos inmobiliarios suelen traer errores de superficie, moneda, comuna,
  coordenadas e imagenes duplicadas.
- Geometrias prediales publicas pueden no estar disponibles para todas las
  comunas o pueden ser referenciales.
- Capas GIS pueden estar en distintos CRS, escalas y fechas de vigencia.
- Distancia peatonal requiere red caminable; distancia recta debe quedar como
  fallback declarado.
- Procesamiento de DEM, pendientes y grandes capas puede exigir cache, jobs y
  formatos columnares.
- Flutter debe administrar correctamente el ciclo de vida del proceso Python.

## Riesgos legales y de cumplimiento

- No automatizar accesos protegidos por Clave Unica, cuentas privadas o
  sesiones no autorizadas.
- No intentar eludir CAPTCHA, rate limits, bloqueos ni mecanismos anti-bot.
- No recolectar datos personales innecesarios de propietarios o deudores.
- La informacion de remates puede contener datos sensibles; debe limitarse a lo
  estrictamente necesario para evaluar oportunidad y evidencia publica.
- Ningun resultado reemplaza CIP, estudio de titulos, tasacion, factibilidades,
  revision DOM, revision SERVIU ni asesoria legal/urbanistica.
- Las reglas DS49/DS19 dependen del llamado, resolucion, region, comuna y fecha.
  Sin fuente normativa vigente se debe usar `UNKNOWN`.

## Mitigaciones

- Auditoria de fuente previa a cada conector.
- Conectores con rate limit, backoff, cache, `Retry-After` y circuit breaker.
- Fixtures HTML/JSON por fuente para detectar cambios.
- Trazabilidad por cada valor derivado.
- Estados `TO_VERIFY`, `MANUAL_REVIEW_REQUIRED`, `BLOCKED` y
  `INFORMACION_INSUFICIENTE`.
- Separacion clara entre cercania a infraestructura y factibilidad formal.
