import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:url_launcher/url_launcher.dart';

class LandfinderMapScreen extends StatelessWidget {
  const LandfinderMapScreen({
    super.key,
    required this.properties,
    required this.selectedProperty,
    required this.territoryByProperty,
    required this.showLandLayer,
    required this.showUrbanLimitLayer,
    required this.showRiskLayer,
    required this.showZoningLayer,
    required this.refreshingTerritory,
    required this.onLandLayerChanged,
    required this.onUrbanLimitLayerChanged,
    required this.onRiskLayerChanged,
    required this.onZoningLayerChanged,
    required this.onSelectProperty,
    required this.onRefreshTerritory,
    this.tileUrlTemplate = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    this.tileAttributionUrl = 'https://www.openstreetmap.org/copyright',
    this.onMapTap,
    this.onViewTerritory,
  });

  final List<Map<String, dynamic>> properties;
  final Map<String, dynamic>? selectedProperty;
  final Map<String, Map<String, dynamic>> territoryByProperty;
  final bool showLandLayer;
  final bool showUrbanLimitLayer;
  final bool showRiskLayer;
  final bool showZoningLayer;
  final bool refreshingTerritory;
  final ValueChanged<bool> onLandLayerChanged;
  final ValueChanged<bool> onUrbanLimitLayerChanged;
  final ValueChanged<bool> onRiskLayerChanged;
  final ValueChanged<bool> onZoningLayerChanged;
  final ValueChanged<Map<String, dynamic>> onSelectProperty;
  final VoidCallback onRefreshTerritory;
  final String tileUrlTemplate;
  final String tileAttributionUrl;
  final ValueChanged<LatLng>? onMapTap;
  final ValueChanged<Map<String, dynamic>>? onViewTerritory;

  @override
  Widget build(BuildContext context) {
    final selected = selectedProperty ?? _firstPropertyWithPoint(properties);
    final selectedTerritory = _selectedTerritory(selected);
    final landPolygons = showLandLayer
        ? _landPolygons(properties)
        : <List<LatLng>>[];
    final urbanPolygons = showUrbanLimitLayer
        ? _arcgisPolygons(selectedTerritory?['urban_limit'])
        : <List<LatLng>>[];
    final riskPolygons = showRiskLayer
        ? _arcgisPolygons(selectedTerritory?['risk_intersection'])
        : <List<LatLng>>[];
    final zoningPolygons = showZoningLayer
        ? _arcgisPolygons(selectedTerritory?['prc'])
        : <List<LatLng>>[];
    final markers = showLandLayer ? _markers(context, selected) : <Marker>[];
    final selectedHasPoint =
        selected != null && _propertyPoint(selected) != null;
    final center =
        _initialCenter(selected) ??
        _firstPoint(properties) ??
        const LatLng(-33.4489, -70.6693);

    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: 10,
            runSpacing: 10,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              FilterChip(
                selected: showLandLayer,
                avatar: const Icon(Icons.place_outlined, size: 18),
                label: const Text('Terrenos'),
                onSelected: onLandLayerChanged,
              ),
              FilterChip(
                selected: showUrbanLimitLayer,
                avatar: const Icon(Icons.domain_outlined, size: 18),
                label: const Text('Limites urbanos'),
                onSelected: onUrbanLimitLayerChanged,
              ),
              FilterChip(
                selected: showRiskLayer,
                avatar: const Icon(Icons.warning_amber_outlined, size: 18),
                label: const Text('Areas de riesgo'),
                onSelected: onRiskLayerChanged,
              ),
              FilterChip(
                selected: showZoningLayer,
                avatar: const Icon(Icons.layers_outlined, size: 18),
                label: const Text('Zonificacion'),
                onSelected: onZoningLayerChanged,
              ),
              const FilterChip(
                selected: false,
                avatar: Icon(Icons.account_balance_outlined, size: 18),
                label: Text('Equipamiento'),
                onSelected: null,
                tooltip: 'Fuente aun no integrada',
              ),
              const FilterChip(
                selected: false,
                avatar: Icon(Icons.alt_route_outlined, size: 18),
                label: Text('Infraestructura'),
                onSelected: null,
                tooltip: 'Fuente aun no integrada',
              ),
              FilledButton.icon(
                onPressed:
                    selected == null || !selectedHasPoint || refreshingTerritory
                    ? null
                    : onRefreshTerritory,
                icon: refreshingTerritory
                    ? const SizedBox.square(
                        dimension: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.travel_explore_outlined),
                label: Text(
                  refreshingTerritory
                      ? 'Consultando MINVU'
                      : 'Actualizar informacion territorial',
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          ClipRRect(
            borderRadius: BorderRadius.circular(8),
            child: Container(
              height: 560,
              decoration: BoxDecoration(
                border: Border.all(color: const Color(0xFFE2E8F0)),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Stack(
                children: [
                  FlutterMap(
                    options: MapOptions(
                      initialCenter: center,
                      initialZoom: _pointCount(properties) <= 1 ? 13 : 10,
                      minZoom: 4,
                      maxZoom: 19,
                      onTap: onMapTap == null
                          ? null
                          : (_, point) => onMapTap!(point),
                    ),
                    children: [
                      TileLayer(
                        urlTemplate: tileUrlTemplate,
                        userAgentPackageName: 'cl.landfinder.desktop',
                      ),
                      if (urbanPolygons.isNotEmpty)
                        PolygonLayer(
                          polygons: _toPolygons(
                            urbanPolygons,
                            fill: Colors.transparent,
                            stroke: const Color(0xFF2563EB),
                            strokeWidth: 2.5,
                          ),
                        ),
                      if (riskPolygons.isNotEmpty)
                        PolygonLayer(
                          polygons: _toPolygons(
                            riskPolygons,
                            fill: const Color(0x33DC2626),
                            stroke: const Color(0xFFDC2626),
                            strokeWidth: 2,
                          ),
                        ),
                      if (zoningPolygons.isNotEmpty)
                        PolygonLayer(
                          polygons: _toPolygons(
                            zoningPolygons,
                            fill: const Color(0x22F59E0B),
                            stroke: const Color(0xFFF59E0B),
                            strokeWidth: 2,
                          ),
                        ),
                      if (landPolygons.isNotEmpty)
                        PolygonLayer(
                          polygons: _toPolygons(
                            landPolygons,
                            fill: const Color(0x3314B8A6),
                            stroke: const Color(0xFF0F766E),
                            strokeWidth: 2,
                          ),
                        ),
                      if (markers.isNotEmpty) MarkerLayer(markers: markers),
                    ],
                  ),
                  if (showLandLayer && _pointCount(properties) == 0)
                    const Positioned.fill(child: _MapEmptyState()),
                  Positioned(
                    left: 12,
                    bottom: 12,
                    child: _MapAttribution(
                      onTap: () => _openUri(tileAttributionUrl),
                    ),
                  ),
                  Positioned(
                    right: 12,
                    top: 12,
                    child: _LayerLegend(
                      propertyCount: _pointCount(properties),
                      hasUrbanLayer: urbanPolygons.isNotEmpty,
                      hasRiskLayer: riskPolygons.isNotEmpty,
                      hasParcelLayer: landPolygons.isNotEmpty,
                      hasZoningLayer: zoningPolygons.isNotEmpty,
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _SmallMapStat(
                label: 'Con coordenadas',
                value: '${_pointCount(properties)}',
              ),
              _SmallMapStat(
                label: 'Total tabla',
                value: '${properties.length}',
              ),
              _SmallMapStat(
                label: 'Poligonos visibles',
                value:
                    '${landPolygons.length + urbanPolygons.length + riskPolygons.length + zoningPolygons.length}',
              ),
            ],
          ),
        ],
      ),
    );
  }

  Map<String, dynamic>? _selectedTerritory(Map<String, dynamic>? selected) {
    final id = selected?['internal_id']?.toString();
    if (id == null) {
      return null;
    }
    return territoryByProperty[id];
  }

  List<Marker> _markers(BuildContext context, Map<String, dynamic>? selected) {
    return [
      for (final property in properties)
        if (_propertyPoint(property) != null)
          Marker(
            point: _propertyPoint(property)!,
            width: _isSelected(property, selected) ? 230 : 46,
            height: _isSelected(property, selected) ? 178 : 46,
            child: _isSelected(property, selected)
                ? _SelectedPropertyMarker(
                    property: property,
                    onTap: () => onSelectProperty(property),
                    onViewTerritory: onViewTerritory == null
                        ? null
                        : () => onViewTerritory!(property),
                  )
                : Tooltip(
                    message: _propertyTitle(property),
                    child: IconButton.filled(
                      onPressed: () => onSelectProperty(property),
                      icon: const Icon(Icons.location_on_outlined, size: 20),
                      style: IconButton.styleFrom(
                        backgroundColor: _markerColor(property),
                        foregroundColor: Colors.white,
                      ),
                    ),
                  ),
          ),
    ];
  }

  bool _isSelected(
    Map<String, dynamic> property,
    Map<String, dynamic>? selected,
  ) {
    return selected?['internal_id']?.toString() ==
        property['internal_id']?.toString();
  }
}

class _SelectedPropertyMarker extends StatelessWidget {
  const _SelectedPropertyMarker({
    required this.property,
    required this.onTap,
    required this.onViewTerritory,
  });

  final Map<String, dynamic> property;
  final VoidCallback onTap;
  final VoidCallback? onViewTerritory;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Material(
        elevation: 4,
        color: Colors.white,
        borderRadius: BorderRadius.circular(8),
        child: Padding(
          padding: const EdgeInsets.all(8),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.only(top: 3),
                child: Icon(
                  Icons.location_on,
                  color: _markerColor(property),
                  size: 22,
                ),
              ),
              const SizedBox(width: 6),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      _propertyTitle(property),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        fontWeight: FontWeight.w900,
                        color: const Color(0xFF0F172A),
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      '${_knownText(property['source'])} | ${_priceText(property)}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                    Text(
                      '${_knownNumber(property['gross_area_m2'], suffix: ' m2')} | ${_knownText(property['commune'])}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: const Color(0xFF64748B),
                      ),
                    ),
                    Text(
                      _coordinatesText(property),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: const Color(0xFF64748B),
                      ),
                    ),
                    Text(
                      _knownText(property['region']),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: const Color(0xFF64748B),
                      ),
                    ),
                    Text(
                      '${_locationLabel(property)} | ${_knownText(property['territorial_status'])}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: _markerColor(property),
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    if (onViewTerritory != null)
                      Align(
                        alignment: Alignment.centerLeft,
                        child: TextButton(
                          onPressed: onViewTerritory,
                          style: TextButton.styleFrom(
                            padding: EdgeInsets.zero,
                            minimumSize: const Size(0, 24),
                            tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                          ),
                          child: const Text('Ver analisis territorial'),
                        ),
                      ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _LayerLegend extends StatelessWidget {
  const _LayerLegend({
    required this.propertyCount,
    required this.hasUrbanLayer,
    required this.hasRiskLayer,
    required this.hasParcelLayer,
    required this.hasZoningLayer,
  });

  final int propertyCount;
  final bool hasUrbanLayer;
  final bool hasRiskLayer;
  final bool hasParcelLayer;
  final bool hasZoningLayer;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.white,
      elevation: 2,
      borderRadius: BorderRadius.circular(8),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            _LegendLine(
              color: const Color(0xFF0F766E),
              label: 'Terrenos: $propertyCount',
            ),
            _LegendLine(
              color: const Color(0xFF2563EB),
              label: hasUrbanLayer
                  ? 'Limite urbano'
                  : 'Limite urbano: sin capa',
            ),
            _LegendLine(
              color: const Color(0xFFDC2626),
              label: hasRiskLayer ? 'Area de riesgo' : 'Riesgo: sin capa',
            ),
            _LegendLine(
              color: const Color(0xFF14B8A6),
              label: hasParcelLayer
                  ? 'Poligono predial'
                  : 'Predio: sin poligono',
            ),
            _LegendLine(
              color: const Color(0xFFF59E0B),
              label: hasZoningLayer ? 'Zonificacion' : 'Zona: sin geometria',
            ),
          ],
        ),
      ),
    );
  }
}

class _LegendLine extends StatelessWidget {
  const _LegendLine({required this.color, required this.label});

  final Color color;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 10,
            height: 10,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          const SizedBox(width: 6),
          Text(label, style: Theme.of(context).textTheme.bodySmall),
        ],
      ),
    );
  }
}

class _MapAttribution extends StatelessWidget {
  const _MapAttribution({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.white.withValues(alpha: 0.92),
      borderRadius: BorderRadius.circular(6),
      child: InkWell(
        borderRadius: BorderRadius.circular(6),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
          child: Text(
            '(c) OpenStreetMap contributors',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
              color: const Color(0xFF334155),
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
      ),
    );
  }
}

class _SmallMapStat extends StatelessWidget {
  const _SmallMapStat({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.white,
        border: Border.all(color: const Color(0xFFE2E8F0)),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            label,
            style: Theme.of(
              context,
            ).textTheme.bodySmall?.copyWith(color: const Color(0xFF64748B)),
          ),
          const SizedBox(width: 8),
          Text(
            value,
            style: Theme.of(
              context,
            ).textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w800),
          ),
        ],
      ),
    );
  }
}

class _MapEmptyState extends StatelessWidget {
  const _MapEmptyState();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Material(
        color: Colors.white.withValues(alpha: 0.92),
        borderRadius: BorderRadius.circular(8),
        child: const Padding(
          padding: EdgeInsets.symmetric(horizontal: 18, vertical: 14),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Icons.location_off_outlined,
                size: 24,
                color: Color(0xFF64748B),
              ),
              SizedBox(width: 10),
              Text('No hay candidatos con ubicacion verificable.'),
            ],
          ),
        ),
      ),
    );
  }
}

List<Polygon> _toPolygons(
  List<List<LatLng>> rings, {
  required Color fill,
  required Color stroke,
  required double strokeWidth,
}) {
  return [
    for (final ring in rings)
      Polygon(
        points: ring,
        color: fill,
        borderColor: stroke,
        borderStrokeWidth: strokeWidth,
      ),
  ];
}

List<List<LatLng>> _landPolygons(List<Map<String, dynamic>> properties) {
  final polygons = <List<LatLng>>[];
  for (final property in properties) {
    polygons.addAll(
      _geoJsonRings(_decodeMaybeJson(property['parcel_geometry'])),
    );
  }
  return polygons;
}

List<List<LatLng>> _arcgisPolygons(dynamic value) {
  final payload = _asMap(value);
  final geometries = payload['matched_geometries'];
  if (geometries is! List) {
    return [];
  }
  final rings = <List<LatLng>>[];
  for (final geometry in geometries) {
    final map = _asMap(geometry);
    final arcgisRings = map['rings'];
    if (arcgisRings is List) {
      rings.addAll(_ringsFromCoordinateList(arcgisRings));
    }
  }
  return rings;
}

List<List<LatLng>> _geoJsonRings(dynamic value) {
  final geojson = _asMap(value);
  final type = geojson['type']?.toString();
  final coordinates = geojson['coordinates'];
  if (type == 'Polygon' && coordinates is List) {
    return _ringsFromCoordinateList(coordinates);
  }
  if (type == 'MultiPolygon' && coordinates is List) {
    final rings = <List<LatLng>>[];
    for (final polygon in coordinates) {
      if (polygon is List) {
        rings.addAll(_ringsFromCoordinateList(polygon));
      }
    }
    return rings;
  }
  return [];
}

List<List<LatLng>> _ringsFromCoordinateList(List<dynamic> rings) {
  final result = <List<LatLng>>[];
  for (final ring in rings) {
    if (ring is! List) {
      continue;
    }
    final points = <LatLng>[];
    for (final coordinate in ring) {
      if (coordinate is! List || coordinate.length < 2) {
        continue;
      }
      final lon = _asDouble(coordinate[0]);
      final lat = _asDouble(coordinate[1]);
      if (lat != null && lon != null && _isValidLatLng(lat, lon)) {
        points.add(LatLng(lat, lon));
      }
    }
    if (points.length >= 3) {
      result.add(points);
    }
  }
  return result;
}

Map<String, dynamic>? _firstPropertyWithPoint(
  List<Map<String, dynamic>> properties,
) {
  for (final property in properties) {
    if (_propertyPoint(property) != null) {
      return property;
    }
  }
  return null;
}

LatLng? _firstPoint(List<Map<String, dynamic>> properties) {
  for (final property in properties) {
    final point = _propertyPoint(property);
    if (point != null) {
      return point;
    }
  }
  return null;
}

LatLng? _initialCenter(Map<String, dynamic>? property) {
  if (property == null) {
    return null;
  }
  return _propertyPoint(property);
}

LatLng? _propertyPoint(Map<String, dynamic> property) {
  final precision = property['location_precision']?.toString() ?? 'UNKNOWN';
  if (!_mappablePrecision(precision)) {
    return null;
  }
  final lat = _asDouble(property['latitude']);
  final lon = _asDouble(property['longitude']);
  if (lat == null || lon == null || !_isValidLatLng(lat, lon)) {
    return null;
  }
  return LatLng(lat, lon);
}

bool _mappablePrecision(String precision) {
  return {
    'EXACT',
    'APPROXIMATE',
    'CENTROID',
    'APPROXIMATE_PROPERTY',
    'PROPERTY_COMMUNE_CENTROID',
  }.contains(precision);
}

bool _isValidLatLng(double lat, double lon) {
  return lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180;
}

int _pointCount(List<Map<String, dynamic>> properties) {
  return properties
      .where((property) => _propertyPoint(property) != null)
      .length;
}

dynamic _decodeMaybeJson(dynamic value) {
  if (value == null) {
    return null;
  }
  if (value is! String) {
    return value;
  }
  try {
    return jsonDecode(value);
  } catch (_) {
    return value;
  }
}

Map<String, dynamic> _asMap(dynamic value) {
  final decoded = _decodeMaybeJson(value);
  if (decoded is Map) {
    return Map<String, dynamic>.from(decoded);
  }
  return {};
}

double? _asDouble(dynamic value) {
  if (value is num) {
    return value.toDouble();
  }
  if (value is String) {
    return double.tryParse(value);
  }
  return null;
}

String _propertyTitle(Map<String, dynamic> property) {
  final title = property['publication_title']?.toString().trim();
  if (title == null || title.isEmpty) {
    return 'Propiedad';
  }
  return title;
}

String _priceText(Map<String, dynamic> property) {
  final uf = _asDouble(property['asking_price_uf']);
  if (uf != null) {
    return '${uf.toStringAsFixed(0)} UF';
  }
  final clp = _asDouble(property['asking_price_clp']);
  if (clp != null) {
    return '\$${clp.toStringAsFixed(0)} CLP';
  }
  return 'Sin precio';
}

String _knownText(dynamic value) {
  final text = _decodeMaybeJson(value)?.toString().trim() ?? '';
  if (text.isEmpty || text == 'null' || text == 'UNKNOWN') {
    return 'Sin informacion';
  }
  return text;
}

String _knownNumber(dynamic value, {String suffix = ''}) {
  final number = _asDouble(value);
  if (number == null) {
    return 'Sin informacion';
  }
  final formatted = number.abs() >= 100
      ? number.round().toString()
      : number.toStringAsFixed(2);
  return '$formatted$suffix';
}

String _coordinatesText(Map<String, dynamic> property) {
  final latitude = _asDouble(property['latitude']);
  final longitude = _asDouble(property['longitude']);
  if (latitude == null || longitude == null) {
    return 'Coordenadas: sin informacion';
  }
  return 'Coord: ${latitude.toStringAsFixed(6)}, ${longitude.toStringAsFixed(6)}';
}

Color _markerColor(Map<String, dynamic> property) {
  final method = property['location_method']?.toString().toLowerCase();
  final precision = property['location_precision']?.toString() ?? 'UNKNOWN';
  if (method == 'manual') {
    return const Color(0xFF7C3AED);
  }
  if (precision == 'EXACT' || precision == 'APPROXIMATE_PROPERTY') {
    return const Color(0xFF047857);
  }
  if (precision == 'PROPERTY_COMMUNE_CENTROID' || precision == 'CENTROID') {
    return const Color(0xFFB45309);
  }
  return const Color(0xFF64748B);
}

String _locationLabel(Map<String, dynamic> property) {
  final method = property['location_method']?.toString().toLowerCase();
  final precision = property['location_precision']?.toString();
  if (method == 'manual') {
    return 'Manual';
  }
  if (precision == 'EXACT') {
    return 'Exacta';
  }
  if (precision == 'APPROXIMATE_PROPERTY' || precision == 'APPROXIMATE') {
    return 'Aproximada';
  }
  if (precision == 'PROPERTY_COMMUNE_CENTROID' || precision == 'CENTROID') {
    return 'Centroide';
  }
  return 'Sin precision';
}

Future<void> _openUri(String url) async {
  final uri = Uri.parse(url);
  await launchUrl(uri, mode: LaunchMode.externalApplication);
}
