# Metro en el MVP v0.7

## Red actual
L1, L2, L3, L4, L4A, L5 y L6 se consultan en relaciones OSM `route=subway`.

Landfinder analiza la geometría completa contra el círculo del terreno:
- SÍ pasa por el área;
- NO pasa;
- distancia mínima.

Las estaciones se consultan en OSM y se asignan espacialmente a las líneas.

## Futuro
### Extensión L6 Poniente
Cerrillos → Av. Suiza → Salvador Allende → Lo Errázuriz.
En 2026 registra avance de construcción y operación proyectada para 2028.

### Extensión L6 Oriente
Los Leones → sector Isidora Goyenechea / Av. Vitacura.
Se desarrolla junto al proyecto L7.

### Línea 7
Renca ↔ Vitacura/Las Condes. 19 estaciones, aprox. 26 km.
Operación proyectada para fines de 2028.

### Línea 8
Los Leones ↔ Puente Alto por ejes Los Leones, Chile España,
José Pedro Alessandri, Macul, La Florida y Camilo Henríquez.
14 estaciones, aprox. 19 km. Puesta en servicio por etapas 2032/2033.

### Línea 9
Puente Cal y Canto ↔ Plaza de Puente Alto por eje Av. Santa Rosa.
19 estaciones, aprox. 27 km. Etapas 2030, 2032 y 2033.

## Regla de seguridad
Si no existe una geometría digital suficientemente confiable:
`NO DETERMINADO`.

Nunca se debe aproximar una línea futura inventando que intersecta un terreno.
