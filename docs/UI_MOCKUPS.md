# Mockups Textuales

## Dashboard

Vista operacional densa, no landing page.

```text
┌─────────────────────────────────────────────────────────────────────┐
│ Terrenos  Nuevos  Preliminares  Observaciones  Incompatibles  Datos │
│ 1.284     87      24            142            31              426   │
├─────────────────────────────────────────────────────────────────────┤
│ Fuentes activas        Errores recientes        Precio UF/m2 neto    │
│ Mercado Publico OK     TocToc TO_VERIFY         insuficiente         │
│ ML API requiere token  SII manual               Superficie neta n/a  │
├─────────────────────────────────────────────────────────────────────┤
│ Ultimas oportunidades y alertas                                      │
│ - Licitacion detectada por keyword "adquisicion terreno"             │
│ - 12 publicaciones sin coordenadas exactas                           │
└─────────────────────────────────────────────────────────────────────┘
```

## Nueva busqueda

```text
Filtros principales
[Region] [Provincia] [Comuna] [Dibujar poligono]
[Precio CLP/UF] [UF/m2 max] [Sup. bruta min] [Sup. neta min]
[Fuentes] [Remates] [Limite urbano] [Vivienda permitida]
[Pendiente max] [Riesgos] [Transporte] [Salud] [Educacion]
[DS49] [DS19] [Calidad minima]

Acciones
[Iniciar busqueda] [Guardar configuracion] [Cancelar]
```

## Resultados

Modo grid:

```text
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ Imagen       │ │ Imagen       │ │ Imagen       │
│ UF 42.000    │ │ $ 890 MM     │ │ UF n/d       │
│ 12.000 m2    │ │ 8.400 m2     │ │ 20.000 m2    │
│ Neto: n/d    │ │ Neto: 6.900  │ │ Neto: n/d    │
│ DS49: insuf. │ │ DS49: obs.   │ │ DS49: manual │
│ Score: n/d   │ │ Score: 61    │ │ Score: n/d   │
└──────────────┘ └──────────────┘ └──────────────┘
```

Modo tabla:

```text
Seleccion  Comuna   Precio   UF/m2 bruto  UF/m2 util  Sup. neta  DS49  DS19  Riesgos  Fuente
[ ]        Maipu    42.000UF 3.5          n/d         n/d        INF   INF   UNKNOWN ML
```

## Mapa

```text
┌ Capas ──────────────┐ ┌────────────────────────────────────────────┐
│ [x] Terrenos        │ │ Mapa con marcadores y poligonos           │
│ [ ] Predios         │ │                                            │
│ [ ] Zonificacion    │ │ Color por compatibilidad preliminar        │
│ [ ] Limite urbano   │ │ Click abre resumen lateral                 │
│ [ ] Riesgos         │ │                                            │
│ [ ] Transporte      │ │                                            │
└─────────────────────┘ └────────────────────────────────────────────┘
```

## Detalle del terreno

Tabs:

```text
Resumen | Comercial | Geometria | Normativa | Riesgos | Infraestructura
Entorno | DS49 | DS19 | Documentos | Evidencias | Imagenes | Historial
```

Cada tab muestra valores, fuente, fecha, confianza y pendientes. El tab DS49 y
DS19 nunca muestra "cumple si/no"; muestra compatibilidad preliminar y reglas.

## Comparador

```text
Terreno             A             B             C
Comuna              Maipu         Pudahuel      Lampa
Precio UF           42.000        38.500        n/d
UF/m2 util          n/d           5.6           n/d
Sup. neta           n/d           6.900         n/d
Forma               UNKNOWN       78/100        UNKNOWN
Riesgo critico      UNKNOWN       CLEAR         WARNING
DS49 preliminar     INF           OBS           MANUAL
Costo/vivienda      n/d           290 UF        n/d
Calidad datos       55            74            31
```
