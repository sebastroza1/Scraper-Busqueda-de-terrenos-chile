# MercadoLibre Real Estate Audit

Fecha: 2026-08-31

## Estado

`PARTIAL`

La integracion OAuth quedo implementada en Flutter/backend local, pero no se
ejecuto una busqueda live de inmuebles chilenos porque no hay tokens reales
configurados en este entorno. No se falsificaron tokens, categorias ni
resultados.

## Documentacion Oficial Revisada

- Authentication and Authorization:
  https://developers.mercadolibre.cl/en_us/manage-project-apps/authentication-and-authorization
- Items and Searches:
  https://developers.mercadolibre.cl/en_us/api-docs/items-and-searches
- Categorias de inmuebles:
  https://developers.mercadolibre.cl/categorias-inmuebles
- Atributos de inmuebles:
  https://developers.mercadolibre.cl/es_ar/publica-productos/atributos-inmuebles
- Real estate developments / properties:
  https://developers.mercadolibre.cl/en_us/real-estate-developments/list-properties

## Hallazgos

| Tema | Resultado |
|---|---|
| OAuth | La documentacion vigente describe Authorization Code Grant. |
| PKCE | `code_verifier` aplica cuando la aplicacion tiene PKCE habilitado. |
| Access token | Debe enviarse por header `Authorization: Bearer ...`. |
| Refresh token | Es de un solo uso; cada refresh devuelve un refresh token nuevo. |
| Expiracion | El access token expira y debe renovarse antes de llamar APIs protegidas. |
| Errores | 401/403 se tratan como expiracion, credencial invalida o permiso insuficiente. |
| Chile | El sitio pais para Chile es `MLC`. |
| Busqueda | La busqueda documentada usa `/sites/$SITE_ID/search` con filtros. |
| Categorias | Las categorias inmobiliarias se descubren por API, no por lista hardcodeada. |
| Atributos | Los atributos por categoria se obtienen desde `/categories/{category_id}/attributes`. |

## Consulta Real Sin Token

Se intento consultar:

```text
GET https://api.mercadolibre.com/sites/MLC/categories
```

Respuesta:

```json
{
  "message": "At least one policy returned UNAUTHORIZED.",
  "status": 403,
  "code": "PA_UNAUTHORIZED_RESULT_FROM_POLICIES",
  "blocked_by": "PolicyAgent"
}
```

Conclusion: en este entorno no se pudo descubrir categorias chilenas sin OAuth.
La busqueda inmobiliaria real queda pendiente de token y no se debe hardcodear
una categoria de terrenos/lotes como si estuviera validada.

## Checklist Solicitado

| Punto | Estado |
|---|---|
| 1. Site ID Chile | `MLC`, segun documentacion de MercadoLibre. |
| 2. Categorias inmobiliarias disponibles | Pendiente live con OAuth; endpoint sin token respondio 403. |
| 3. Categoria terrenos/lotes | Pendiente live con OAuth y atributos de categoria. |
| 4. Filtros disponibles | Pendiente por respuesta `available_filters` de `/sites/MLC/search`. |
| 5. Busqueda por ubicacion | Documentada como filtros/parametros de search; pendiente probar cobertura real. |
| 6. Superficie | Pendiente segun atributos de categoria. |
| 7. Precio | Disponible en items/search si el recurso lo retorna. |
| 8. Atributos inmobiliarios | Endpoint documentado, pendiente live por categoria chilena. |
| 9. Imagenes | Disponible en items/search/detalle cuando la API las entregue. |
| 10. Coordenadas | No garantizadas; deben marcarse con precision, no inventarse. |
| 11. Descripcion | Pendiente validar en item detail/description con token. |
| 12. Vendedor | Disponible parcialmente en datos de item; permisos a validar. |
| 13. Paginacion | Documentada en search; pendiente limites reales de cuenta/token. |
| 14. Limites | Pendiente medir con token real y manejo 401/403/429. |

## Implementacion En La App

- `SecretStore` guarda client id, client secret opcional, access token, refresh
  token, expiracion y redirect URI fuera de SQLite/logs/config publica.
- Flutter inicia Authorization Code con PKCE y callback localhost.
- El backend recibe tokens solo mediante sincronizacion local de settings.
- Las consultas MercadoLibre no se ejecutan sin access token.
- El conector conserva estado `PARTIAL` hasta validar cobertura real con token.

## Recursos Relevantes A Probar Con Token

| Recurso | Uso esperado | Estado |
|---|---|---|
| `GET https://api.mercadolibre.com/sites/MLC/categories` | Descubrir categorias chilenas. | Implementado en diagnostico, pendiente live con token. |
| `GET https://api.mercadolibre.com/categories/{category_id}/attributes` | Auditar campos de terrenos/lotes. | Pendiente live con token. |
| `GET https://api.mercadolibre.com/sites/MLC/search` | Buscar publicaciones activas accesibles al token. | Implementado en conector, pendiente live con token. |
| `GET https://api.mercadolibre.com/items/{item_id}` | Detalle de item si la busqueda retorna ids. | Pendiente ampliacion. |

## Limitacion Actual

Con la documentacion revisada se puede afirmar que existe API oficial y OAuth,
pero no que el token del usuario tenga acceso a toda la busqueda inmobiliaria
chilena ni a PortalInmobiliario con la granularidad requerida. Esa cobertura
debe medirse con una cuenta real antes de declarar `ACTIVE`.
