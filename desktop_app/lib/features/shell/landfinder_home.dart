import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../app/router.dart';
import '../../core/api/landfinder_api.dart';
import '../../core/security/secret_store.dart';
import '../map/map_screen.dart';

part '../../core/widgets/common_widgets.dart';

class LandfinderHome extends StatefulWidget {
  const LandfinderHome({super.key, required this.api});

  final LandfinderApi api;

  @override
  State<LandfinderHome> createState() => _LandfinderHomeState();
}

class _LandfinderHomeState extends State<LandfinderHome> {
  static const String _maskedSecret = '********';
  final TextEditingController _keywordAddController = TextEditingController();
  final TextEditingController _resultSearchController = TextEditingController();
  final TextEditingController _areaMinController = TextEditingController(
    text: '1000',
  );
  final TextEditingController _areaMaxController = TextEditingController();
  final TextEditingController _priceMinController = TextEditingController();
  final TextEditingController _priceMaxController = TextEditingController();
  final TextEditingController _mercadoPublicoTicketController =
      TextEditingController();
  final TextEditingController _cmfTokenController = TextEditingController();
  final TextEditingController _mercadoLibreClientIdController =
      TextEditingController();
  final TextEditingController _mercadoLibreClientSecretController =
      TextEditingController();
  final TextEditingController _mercadoLibreRedirectUriController =
      TextEditingController();
  final TextEditingController _mercadoLibrePartnerSellersController =
      TextEditingController();
  final TextEditingController _mercadoLibreImportController =
      TextEditingController();
  final TextEditingController _manualTitleController = TextEditingController();
  final TextEditingController _manualRegionController = TextEditingController();
  final TextEditingController _manualCommuneController =
      TextEditingController();
  final TextEditingController _manualAddressController =
      TextEditingController();
  final TextEditingController _manualLatController = TextEditingController();
  final TextEditingController _manualLonController = TextEditingController();
  final TextEditingController _manualAreaController = TextEditingController();
  final TextEditingController _manualPriceController = TextEditingController();
  final TextEditingController _manualUrlController = TextEditingController();
  final TextEditingController _manualNotesController = TextEditingController();

  AppSection _section = AppSection.dashboard;
  List<Map<String, dynamic>> _sources = [];
  List<Map<String, dynamic>> _enrichmentSources = [];
  List<Map<String, dynamic>> _sourceHealth = [];
  List<Map<String, dynamic>> _regionsCatalog = [];
  List<Map<String, dynamic>> _communesCatalog = [];
  List<Map<String, dynamic>> _keywordPresets = [];
  List<Map<String, dynamic>> _properties = [];
  List<Map<String, dynamic>> _events = [];
  Map<String, dynamic>? _sourceRecords;
  Map<String, dynamic>? _mercadoLibreImportPreview;
  Map<String, dynamic>? _mercadoLibreImportSummary;
  List<Map<String, dynamic>> _mercadoLibreImportHistory = [];
  Map<String, dynamic> _settings = {};
  Map<String, dynamic>? _job;
  Map<String, dynamic>? _audit;
  Map<String, dynamic>? _selectedProperty;
  Map<String, dynamic>? _selectedSourceRecord;
  Map<String, dynamic> _mapProviders = {};
  Map<String, bool> _secretStatus = {};
  final Map<String, Map<String, dynamic>> _credentialDiagnostics = {};
  final Map<String, Map<String, dynamic>> _territoryByProperty = {};
  Set<String> _selectedSources = {};
  Set<String> _selectedEnrichmentSources = {'cmf_uf', 'minvu'};
  Map<String, dynamic>? _selectedCommune;
  final Map<String, bool> _keywordEnabled = {};
  String? _selectedRegionCode = 'ALL';
  String _keywordMode = 'ANY';
  String? _latestSearchId;
  String _sourceRecordBucket = 'candidates';
  Timer? _jobTimer;
  bool _booting = true;
  bool _searching = false;
  bool _discoverSoilMode = false;
  bool _discoveringSoil = false;
  bool _soilOnlyInsideUrbanLimit = false;
  bool _savingSettings = false;
  String? _testingCredentialSource;
  bool _connectingMercadoLibre = false;
  bool _analyzingMercadoLibreImport = false;
  bool _importingMercadoLibreItems = false;
  bool _importVacantLand = true;
  bool _importLandWithStructure = true;
  bool _importUnknownLand = false;
  bool _importNonLandProperty = false;
  bool _refreshingTerritory = false;
  bool _showLandLayer = true;
  bool _showUrbanLimitLayer = true;
  bool _showRiskLayer = true;
  bool _showZoningLayer = true;
  bool _showPotentialStatus = true;
  bool _showReviewStatus = true;
  bool _showUnsuitableStatus = true;
  bool _showInsufficientStatus = true;
  bool _exporting = false;
  String? _error;
  String? _exportPath;

  @override
  void initState() {
    super.initState();
    _bootstrap();
  }

  @override
  void dispose() {
    _jobTimer?.cancel();
    _keywordAddController.dispose();
    _resultSearchController.dispose();
    _areaMinController.dispose();
    _areaMaxController.dispose();
    _priceMinController.dispose();
    _priceMaxController.dispose();
    _mercadoPublicoTicketController.dispose();
    _cmfTokenController.dispose();
    _mercadoLibreClientIdController.dispose();
    _mercadoLibreClientSecretController.dispose();
    _mercadoLibreRedirectUriController.dispose();
    _mercadoLibrePartnerSellersController.dispose();
    _mercadoLibreImportController.dispose();
    _manualTitleController.dispose();
    _manualRegionController.dispose();
    _manualCommuneController.dispose();
    _manualAddressController.dispose();
    _manualLatController.dispose();
    _manualLonController.dispose();
    _manualAreaController.dispose();
    _manualPriceController.dispose();
    _manualUrlController.dispose();
    _manualNotesController.dispose();
    widget.api.dispose();
    super.dispose();
  }

  Future<void> _bootstrap() async {
    setState(() {
      _booting = true;
      _error = null;
    });
    try {
      await widget.api.start();
      await _refreshAll();
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() => _error = error.toString());
    } finally {
      if (mounted) {
        setState(() => _booting = false);
      }
    }
  }

  Future<void> _refreshAll() async {
    final results = await Future.wait<dynamic>([
      widget.api.sources(),
      widget.api.enrichmentSources(),
      widget.api.sourcesHealth(),
      widget.api.regions(),
      widget.api.communes(_selectedRegionCode ?? 'ALL'),
      widget.api.keywordPresets(),
      widget.api.settings(),
      widget.api.properties(),
      widget.api.secretStatus(),
      widget.api.mapProviders(),
    ]);
    if (!mounted) {
      return;
    }
    final sources = List<Map<String, dynamic>>.from(results[0] as List);
    final enrichmentSources = List<Map<String, dynamic>>.from(
      results[1] as List,
    );
    final regionsPayload = Map<String, dynamic>.from(results[3] as Map);
    final communesPayload = Map<String, dynamic>.from(results[4] as Map);
    final presetsPayload = Map<String, dynamic>.from(results[5] as Map);
    final propertiesPayload = Map<String, dynamic>.from(results[7] as Map);
    final sourceIds = sources
        .map((source) => source['source_id'].toString())
        .toSet();
    final enrichmentIds = enrichmentSources
        .map((source) => source['source_id'].toString())
        .toSet();
    setState(() {
      _sources = sources;
      _enrichmentSources = enrichmentSources;
      _sourceHealth = List<Map<String, dynamic>>.from(results[2] as List);
      _regionsCatalog = List<Map<String, dynamic>>.from(
        regionsPayload['items'] as List? ?? const [],
      );
      _communesCatalog = List<Map<String, dynamic>>.from(
        communesPayload['items'] as List? ?? const [],
      );
      _keywordPresets = List<Map<String, dynamic>>.from(
        presetsPayload['items'] as List? ?? const [],
      );
      _ensureDefaultKeywords();
      _settings = Map<String, dynamic>.from(results[6] as Map);
      _syncMercadoLibreCredentialFields();
      _properties = List<Map<String, dynamic>>.from(
        propertiesPayload['items'] as List? ?? const [],
      );
      _secretStatus = Map<String, bool>.from(results[8] as Map);
      _mapProviders = Map<String, dynamic>.from(results[9] as Map);
      if (_regionsCatalog.isEmpty ||
          !(_selectedRegionCode == 'ALL' ||
              _regionsCatalog.any(
                (item) => item['code'] == _selectedRegionCode,
              ))) {
        _selectedRegionCode = 'ALL';
      }
      if (_selectedSources.isEmpty) {
        _selectedSources = sourceIds;
      } else {
        _selectedSources = _selectedSources.intersection(sourceIds);
        if (_selectedSources.isEmpty) {
          _selectedSources = sourceIds;
        }
      }
      _selectedEnrichmentSources = _selectedEnrichmentSources.intersection(
        enrichmentIds,
      );
      if (_selectedEnrichmentSources.isEmpty) {
        _selectedEnrichmentSources = {
          'cmf_uf',
          'minvu',
        }.intersection(enrichmentIds);
      }
      if (_selectedCommune != null &&
          !_communesCatalog.any(
            (item) => item['commune_id'] == _selectedCommune?['commune_id'],
          )) {
        _selectedCommune = null;
      }
      _validateSelectedResult();
    });
    if (_latestSearchId != null) {
      await _refreshSourceRecords();
    }
  }

  Future<void> _startSearch() async {
    if (_selectedSources.isEmpty) {
      setState(() => _error = 'Selecciona al menos una fuente.');
      return;
    }
    setState(() {
      _searching = true;
      _error = null;
      _events = [];
      _job = null;
      _sourceRecords = null;
      _selectedSourceRecord = null;
      _section = AppSection.search;
    });
    try {
      final response = await widget.api.startSearch(_buildFilters());
      final searchId = response['search_id'].toString();
      _latestSearchId = searchId;
      await _pollJob(searchId);
      _jobTimer?.cancel();
      _jobTimer = Timer.periodic(
        const Duration(seconds: 1),
        (_) => _pollJob(searchId),
      );
    } catch (error) {
      if (mounted) {
        setState(() {
          _error = error.toString();
          _searching = false;
        });
      }
    }
  }

  Future<void> _discoverSoil() async {
    setState(() {
      _discoveringSoil = true;
      _error = null;
    });
    try {
      final payload = await widget.api.discoverSoil({
        'region': _selectedRegionName(),
        'commune': _selectedCommuneName(),
        'bbox': _soilDiscoveryBbox(),
        'surface_min_m2': _numOrNull(_areaMinController.text),
        'surface_max_m2': _numOrNull(_areaMaxController.text),
        'limit': 100,
        'offset': 0,
        'only_inside_urban_limit': _soilOnlyInsideUrbanLimit,
      });
      if (mounted) {
        final items = List<Map<String, dynamic>>.from(
          payload['items'] as List? ?? const [],
        );
        setState(() {
          _properties = items;
          _sourceRecords = {
            'items': [
              for (final item in items) _soilSourceRecord(item),
            ],
          };
          _section = AppSection.results;
        });
      }
      await _refreshAll();
    } catch (error) {
      if (mounted) {
        setState(() => _error = error.toString());
      }
    } finally {
      if (mounted) {
        setState(() => _discoveringSoil = false);
      }
    }
  }

  Future<void> _pollJob(String searchId) async {
    try {
      final job = await widget.api.search(searchId);
      final events = List<Map<String, dynamic>>.from(
        job['events'] as List? ?? const [],
      );
      final status = job['status'].toString();
      final isActive =
          status == 'QUEUED' || status == 'RUNNING' || status == 'CANCELLING';
      if (!mounted) {
        return;
      }
      setState(() {
        _job = job;
        _events = events.reversed.take(80).toList().reversed.toList();
        _searching = isActive;
      });
      if (!isActive) {
        _jobTimer?.cancel();
        await _refreshAll();
        await _refreshSourceRecords();
      }
    } catch (error) {
      if (mounted) {
        setState(() {
          _error = error.toString();
          _searching = false;
        });
      }
      _jobTimer?.cancel();
    }
  }

  Map<String, dynamic> _buildFilters() {
    return {
      'regions': [
        if (_selectedRegionCode != null && _selectedRegionCode != 'ALL')
          _selectedRegionCode,
      ],
      'communes': [if (_selectedCommuneName() != null) _selectedCommuneName()],
      'keywords': _activeKeywords(),
      'keyword_mode': _keywordMode,
      'sources': _selectedSources.toList()..sort(),
      'search_sources': _selectedSources.toList()..sort(),
      'enrichment_sources': _selectedEnrichmentSources.toList()..sort(),
      'gross_area_min_m2': _parseDouble(_areaMinController.text),
      'gross_area_max_m2': _parseDouble(_areaMaxController.text),
      'price_min_clp': _parseInt(_priceMinController.text),
      'price_max_clp': _parseInt(_priceMaxController.text),
      'include_auctions': true,
    }..removeWhere((_, value) => value == null);
  }

  void _ensureDefaultKeywords() {
    if (_keywordEnabled.isNotEmpty || _keywordPresets.isEmpty) {
      return;
    }
    final preset = _keywordPresets.firstWhere(
      (item) => item['id'] == 'BUSQUEDA_TERRENOS_CHILE',
      orElse: () => _keywordPresets.first,
    );
    _applyPreset(preset, replace: true);
  }

  List<String> _activeKeywords() {
    return [
      for (final entry in _keywordEnabled.entries)
        if (entry.value) entry.key,
    ];
  }

  List<String> _activeAdditionalKeywords() {
    final presetKeywords = <String>{};
    for (final preset in _keywordPresets) {
      if (preset['id'] != 'BUSQUEDA_TERRENOS_CHILE') {
        continue;
      }
      for (final item in preset['keywords'] as List? ?? const []) {
        presetKeywords.add(item.toString());
      }
    }
    return [
      for (final keyword in _activeKeywords())
        if (!presetKeywords.contains(keyword)) keyword,
    ];
  }

  Future<void> _loadCommunes(String regionCode) async {
    final payload = await widget.api.communes(regionCode);
    if (!mounted) {
      return;
    }
    final communes = List<Map<String, dynamic>>.from(
      payload['items'] as List? ?? const [],
    );
    setState(() {
      _communesCatalog = communes;
      if (_selectedCommune != null &&
          !communes.any(
            (item) => item['commune_id'] == _selectedCommune?['commune_id'],
          )) {
        _selectedCommune = null;
      }
    });
  }

  void _applyPreset(Map<String, dynamic> preset, {required bool replace}) {
    final keywords = (preset['keywords'] as List? ?? const [])
        .map((item) => item.toString().trim())
        .where((item) => item.isNotEmpty);
    if (replace) {
      _keywordEnabled.clear();
    }
    for (final keyword in keywords) {
      _keywordEnabled.putIfAbsent(keyword, () => true);
    }
    final mode = preset['default_mode']?.toString();
    if (mode == 'ANY' || mode == 'ALL') {
      _keywordMode = mode!;
    }
  }

  void _addKeyword() {
    final keyword = _keywordAddController.text.trim();
    if (keyword.isEmpty) {
      return;
    }
    setState(() {
      _keywordEnabled[keyword] = true;
      _keywordAddController.clear();
    });
  }

  Future<void> _refreshSourceRecords() async {
    final searchId = _latestSearchId;
    if (searchId == null) {
      return;
    }
    final records = await widget.api.searchSourceRecords(
      searchId,
      bucket: _sourceRecordBucket,
      limit: 500,
    );
    if (mounted) {
      setState(() {
        _sourceRecords = records;
        _validateSelectedResult();
      });
    }
  }

  String? _selectedCommuneName() {
    return _selectedCommune?['commune_name']?.toString() ??
        _selectedCommune?['name']?.toString();
  }

  String? _selectedCommuneRegionCode() {
    return _selectedCommune?['region_id']?.toString() ??
        _selectedCommune?['region_code']?.toString();
  }

  String? _selectedRegionName() {
    final code = _selectedRegionCode;
    if (code == null || code == 'ALL') {
      return null;
    }
    for (final region in _regionsCatalog) {
      if (region['code']?.toString() == code) {
        return region['name']?.toString();
      }
    }
    return code;
  }

  List<double> _soilDiscoveryBbox() {
    final commune = _selectedCommuneName()?.toLowerCase() ?? '';
    if (commune.contains('melipilla')) {
      return [-71.30, -33.85, -70.95, -33.55];
    }
    if (commune.contains('talagante')) {
      return [-70.98, -33.78, -70.78, -33.58];
    }
    if (commune.contains('paine')) {
      return [-71.00, -33.95, -70.60, -33.70];
    }
    final region = (_selectedRegionName() ?? '').toLowerCase();
    if (region.contains('metropolitana') || _selectedRegionCode == 'RM') {
      return [-70.95, -33.65, -70.75, -33.45];
    }
    return [-70.95, -33.65, -70.75, -33.45];
  }

  double? _numOrNull(String value) {
    final normalized = value.trim().replaceAll('.', '').replaceAll(',', '.');
    if (normalized.isEmpty) {
      return null;
    }
    return double.tryParse(normalized);
  }

  Map<String, dynamic> _soilSourceRecord(Map<String, dynamic> item) {
    final rawPayload = _decodeMaybeJson(item['raw_payload_json']);
    return {
      'source_record_id': 'soil-${item['internal_id']}',
      'property_id': item['internal_id'],
      'source': item['source'],
      'source_type': item['source_type'],
      'external_id': item['external_id'],
      'title': item['publication_title'],
      'automatic_classification': 'CANDIDATO TERRITORIAL',
      'automatic_confidence': 0.9,
      'property_region': item['region'],
      'property_commune': item['commune'],
      'surface_m2': item['gross_area_m2'] ?? item['geometry_area_m2'],
      'amount': null,
      'currency': null,
      'publication_date': null,
      'organization': 'CIREN',
      'raw_payload': rawPayload,
    };
  }

  String _selectedCommuneSummary() {
    final name = _selectedCommuneName();
    return name == null || name.isEmpty ? 'Todas las comunas' : name;
  }

  void _applyCommuneChoice(Map<String, dynamic>? commune) {
    _selectedCommune = commune;
    final regionCode = commune == null ? null : _selectedCommuneRegionCode();
    if (regionCode != null && regionCode.isNotEmpty) {
      _selectedRegionCode = regionCode;
      unawaited(_loadCommunes(regionCode));
    }
    _validateSelectedResult();
  }

  void _validateSelectedResult() {
    final propertyId = _selectedProperty?['internal_id']?.toString();
    if (propertyId != null && !_visiblePropertyIds().contains(propertyId)) {
      _selectedProperty = null;
    }
    final recordId = _selectedSourceRecord?['source_record_id']?.toString();
    if (recordId != null &&
        !_filteredSourceRecordItems().any(
          (record) => record['source_record_id']?.toString() == recordId,
        )) {
      _selectedSourceRecord = null;
    }
  }

  Set<String> _visiblePropertyIds() {
    final ids = <String>{};
    final records = _filteredSourceRecordItems();
    if (records.isNotEmpty || _sourceRecords != null) {
      for (final record in records) {
        final propertyId = record['property_id']?.toString();
        if (propertyId != null && propertyId.isNotEmpty) {
          ids.add(propertyId);
        }
      }
      return ids;
    }
    for (final property in _properties) {
      final propertyId = property['internal_id']?.toString();
      if (propertyId != null && propertyId.isNotEmpty) {
        ids.add(propertyId);
      }
    }
    return ids;
  }

  Future<void> _updateManualClassification(
    Map<String, dynamic> record,
    String classification,
  ) async {
    final sourceRecordId = record['source_record_id']?.toString();
    if (sourceRecordId == null || sourceRecordId.isEmpty) {
      return;
    }
    setState(() => _error = null);
    try {
      final updated = await widget.api.updateManualClassification(
        sourceRecordId,
        classification,
      );
      if (mounted) {
        setState(() => _selectedSourceRecord = updated);
      }
      await _refreshSourceRecords();
    } catch (error) {
      if (mounted) {
        setState(() => _error = error.toString());
      }
    }
  }

  Future<void> _saveSourceSecret(
    String key,
    TextEditingController controller,
  ) async {
    setState(() {
      _savingSettings = true;
      _error = null;
    });
    try {
      await widget.api.saveSecret(key, controller.text);
      final settings = await widget.api.settings();
      if (!mounted) {
        return;
      }
      setState(() {
        _settings = settings;
        controller.clear();
      });
      await _refreshAll();
    } catch (error) {
      if (mounted) {
        setState(() => _error = error.toString());
      }
    } finally {
      if (mounted) {
        setState(() => _savingSettings = false);
      }
    }
  }

  Future<void> _deleteSourceSecret(String key) async {
    setState(() {
      _savingSettings = true;
      _error = null;
    });
    try {
      await widget.api.deleteSecret(key);
      await _refreshAll();
    } catch (error) {
      if (mounted) {
        setState(() => _error = error.toString());
      }
    } finally {
      if (mounted) {
        setState(() => _savingSettings = false);
      }
    }
  }

  Future<void> _testCredential(String sourceId) async {
    setState(() {
      _testingCredentialSource = sourceId;
      _error = null;
    });
    try {
      final diagnostic = await widget.api.testCredential(sourceId);
      if (mounted) {
        setState(() {
          _credentialDiagnostics[sourceId] = diagnostic;
        });
      }
      await _refreshAll();
    } catch (error) {
      if (mounted) {
        setState(() => _error = error.toString());
      }
    } finally {
      if (mounted) {
        setState(() => _testingCredentialSource = null);
      }
    }
  }

  Future<void> _connectMercadoLibre() async {
    setState(() {
      _connectingMercadoLibre = true;
      _error = null;
    });
    try {
      final clientSecretText = _mercadoLibreClientSecretController.text.trim();
      final result = await widget.api.connectMercadoLibre(
        clientId: _mercadoLibreClientIdController.text,
        clientSecret: clientSecretText == _maskedSecret
            ? null
            : clientSecretText,
        redirectUri: _mercadoLibreRedirectUriController.text,
      );
      if (mounted) {
        setState(() {
          _mercadoLibreClientSecretController.clear();
          _settings['mercadolibre_last_oauth_user_id'] = result['user_id'];
        });
      }
      await _refreshAll();
    } catch (error) {
      if (mounted) {
        setState(() => _error = error.toString());
      }
    } finally {
      if (mounted) {
        setState(() => _connectingMercadoLibre = false);
      }
    }
  }

  Future<void> _analyzeMercadoLibreImport() async {
    setState(() {
      _analyzingMercadoLibreImport = true;
      _error = null;
      _mercadoLibreImportSummary = null;
    });
    try {
      final preview = await widget.api.analyzeMercadoLibreImport(
        _mercadoLibreImportController.text,
      );
      if (mounted) {
        setState(() => _mercadoLibreImportPreview = preview);
      }
    } catch (error) {
      if (mounted) {
        setState(() => _error = error.toString());
      }
    } finally {
      if (mounted) {
        setState(() => _analyzingMercadoLibreImport = false);
      }
    }
  }

  Future<void> _importMercadoLibreItems() async {
    setState(() {
      _importingMercadoLibreItems = true;
      _error = null;
    });
    try {
      final summary = await widget.api.importMercadoLibreItems(
        _mercadoLibreImportController.text,
        _mercadoLibreImportTypes(),
      );
      final history = await widget.api.mercadoLibreImportHistory();
      if (mounted) {
        setState(() {
          _mercadoLibreImportSummary = summary;
          _mercadoLibreImportHistory = List<Map<String, dynamic>>.from(
            history['items'] as List? ?? const [],
          );
        });
      }
      await _refreshAll();
    } catch (error) {
      if (mounted) {
        setState(() => _error = error.toString());
      }
    } finally {
      if (mounted) {
        setState(() => _importingMercadoLibreItems = false);
      }
    }
  }

  void _clearMercadoLibreImport() {
    setState(() {
      _mercadoLibreImportController.clear();
      _mercadoLibreImportPreview = null;
      _mercadoLibreImportSummary = null;
    });
  }

  List<String> _mercadoLibreImportTypes() {
    return [
      if (_importVacantLand) 'VACANT_LAND',
      if (_importLandWithStructure) 'LAND_WITH_STRUCTURE',
      if (_importUnknownLand) 'UNKNOWN',
      if (_importNonLandProperty) 'NON_LAND_PROPERTY',
    ];
  }

  Future<void> _exportExcel() async {
    setState(() {
      _exporting = true;
      _error = null;
      _section = AppSection.exports;
    });
    try {
      final response = await widget.api.exportExcel();
      if (mounted) {
        setState(() => _exportPath = response['path']?.toString());
      }
    } catch (error) {
      if (mounted) {
        setState(() => _error = error.toString());
      }
    } finally {
      if (mounted) {
        setState(() => _exporting = false);
      }
    }
  }

  Future<void> _createManualProperty() async {
    _manualTitleController.clear();
    _manualRegionController.clear();
    _manualCommuneController.clear();
    _manualAddressController.clear();
    _manualLatController.clear();
    _manualLonController.clear();
    _manualAreaController.clear();
    _manualPriceController.clear();
    _manualUrlController.clear();
    _manualNotesController.clear();
    final saved = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Agregar terreno'),
        content: SizedBox(
          width: 720,
          child: SingleChildScrollView(
            child: Wrap(
              spacing: 12,
              runSpacing: 12,
              children: [
                _InputBox(
                  controller: _manualTitleController,
                  label: 'Titulo',
                  icon: Icons.title_outlined,
                ),
                _InputBox(
                  controller: _manualRegionController,
                  label: 'Region',
                  icon: Icons.public_outlined,
                ),
                _InputBox(
                  controller: _manualCommuneController,
                  label: 'Comuna',
                  icon: Icons.location_city_outlined,
                ),
                _InputBox(
                  controller: _manualAddressController,
                  label: 'Direccion',
                  icon: Icons.signpost_outlined,
                ),
                _InputBox(
                  controller: _manualLatController,
                  label: 'Latitud',
                  icon: Icons.my_location_outlined,
                ),
                _InputBox(
                  controller: _manualLonController,
                  label: 'Longitud',
                  icon: Icons.explore_outlined,
                ),
                _InputBox(
                  controller: _manualAreaController,
                  label: 'Superficie m2',
                  icon: Icons.square_foot_outlined,
                ),
                _InputBox(
                  controller: _manualPriceController,
                  label: 'Precio CLP',
                  icon: Icons.payments_outlined,
                ),
                _InputBox(
                  controller: _manualUrlController,
                  label: 'URL',
                  icon: Icons.link_outlined,
                ),
                _InputBox(
                  controller: _manualNotesController,
                  label: 'Observaciones',
                  icon: Icons.notes_outlined,
                ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancelar'),
          ),
          FilledButton.icon(
            onPressed: () => Navigator.of(context).pop(true),
            icon: const Icon(Icons.add_location_alt_outlined),
            label: const Text('Guardar'),
          ),
        ],
      ),
    );
    if (saved != true || _manualTitleController.text.trim().isEmpty) {
      return;
    }
    setState(() => _error = null);
    try {
      final response = await widget.api.createManualProperty(
        {
          'title': _manualTitleController.text.trim(),
          'region': _manualRegionController.text.trim(),
          'commune': _manualCommuneController.text.trim(),
          'address': _manualAddressController.text.trim(),
          'latitude': _parseDouble(_manualLatController.text),
          'longitude': _parseDouble(_manualLonController.text),
          'gross_area_m2': _parseDouble(_manualAreaController.text),
          'asking_price_clp': _parseInt(_manualPriceController.text),
          'url': _manualUrlController.text.trim(),
          'observations': _manualNotesController.text.trim(),
        }..removeWhere((_, value) => value == null || value == ''),
      );
      final property = Map<String, dynamic>.from(response['property'] as Map);
      await _refreshAll();
      if (mounted) {
        setState(() {
          _selectedProperty = property;
          _section = AppSection.map;
        });
      }
    } catch (error) {
      if (mounted) {
        setState(() => _error = error.toString());
      }
    }
  }

  Future<void> _showAssignLocationDialog(Map<String, dynamic> property) async {
    final addressController = TextEditingController(
      text: _knownText(
        property['normalized_address'] ?? property['original_address'],
      ).replaceAll('Sin informacion', ''),
    );
    final regionController = TextEditingController(
      text: _knownText(property['region']).replaceAll('Sin informacion', ''),
    );
    final communeController = TextEditingController(
      text: _knownText(property['commune']).replaceAll('Sin informacion', ''),
    );
    final latController = TextEditingController(
      text: property['latitude']?.toString() ?? '',
    );
    final lonController = TextEditingController(
      text: property['longitude']?.toString() ?? '',
    );
    var geocodeResults = <Map<String, dynamic>>[];
    var searching = false;
    try {
      final assigned = await showDialog<bool>(
        context: context,
        builder: (context) => StatefulBuilder(
          builder: (context, setDialogState) {
            final lat = _parseDouble(latController.text);
            final lon = _parseDouble(lonController.text);
            final point = lat == null || lon == null
                ? const LatLng(-33.4489, -70.6693)
                : LatLng(lat, lon);
            return AlertDialog(
              title: const Text('Asignar ubicacion'),
              content: SizedBox(
                width: 760,
                child: SingleChildScrollView(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Wrap(
                        spacing: 12,
                        runSpacing: 12,
                        children: [
                          _InputBox(
                            controller: addressController,
                            label: 'Direccion',
                            icon: Icons.signpost_outlined,
                          ),
                          _InputBox(
                            controller: communeController,
                            label: 'Comuna',
                            icon: Icons.location_city_outlined,
                          ),
                          _InputBox(
                            controller: regionController,
                            label: 'Region',
                            icon: Icons.public_outlined,
                          ),
                          _InputBox(
                            controller: latController,
                            label: 'Latitud',
                            icon: Icons.my_location_outlined,
                          ),
                          _InputBox(
                            controller: lonController,
                            label: 'Longitud',
                            icon: Icons.explore_outlined,
                          ),
                        ],
                      ),
                      const SizedBox(height: 12),
                      Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: [
                          OutlinedButton.icon(
                            onPressed: searching
                                ? null
                                : () async {
                                    setDialogState(() => searching = true);
                                    try {
                                      final result = await widget.api.geocode({
                                        'address': addressController.text,
                                        'commune': communeController.text,
                                        'region': regionController.text,
                                      });
                                      geocodeResults =
                                          List<Map<String, dynamic>>.from(
                                            (result['candidates'] as List? ??
                                                    const [])
                                                .whereType<Map>()
                                                .map(
                                                  (item) =>
                                                      Map<String, dynamic>.from(
                                                        item,
                                                      ),
                                                ),
                                          );
                                      if (geocodeResults.isNotEmpty) {
                                        latController.text = geocodeResults
                                            .first['latitude']
                                            .toString();
                                        lonController.text = geocodeResults
                                            .first['longitude']
                                            .toString();
                                      }
                                    } finally {
                                      setDialogState(() => searching = false);
                                    }
                                  },
                            icon: searching
                                ? const SizedBox.square(
                                    dimension: 18,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                    ),
                                  )
                                : const Icon(Icons.search_outlined),
                            label: const Text('Buscar direccion'),
                          ),
                        ],
                      ),
                      if (geocodeResults.isNotEmpty) ...[
                        const SizedBox(height: 10),
                        for (final result in geocodeResults.take(3))
                          ListTile(
                            dense: true,
                            leading: const Icon(Icons.place_outlined),
                            title: Text(_knownText(result['display_name'])),
                            subtitle: Text(
                              '${result['latitude']}, ${result['longitude']} | ${_knownText(result['location_precision'])}',
                            ),
                            onTap: () {
                              setDialogState(() {
                                latController.text = result['latitude']
                                    .toString();
                                lonController.text = result['longitude']
                                    .toString();
                                addressController.text = _knownText(
                                  result['display_name'],
                                );
                              });
                            },
                          ),
                      ],
                      const SizedBox(height: 12),
                      SizedBox(
                        height: 300,
                        child: ClipRRect(
                          borderRadius: BorderRadius.circular(8),
                          child: FlutterMap(
                            options: MapOptions(
                              initialCenter: point,
                              initialZoom: 13,
                              onTap: (_, tapped) {
                                setDialogState(() {
                                  latController.text = tapped.latitude
                                      .toStringAsFixed(6);
                                  lonController.text = tapped.longitude
                                      .toStringAsFixed(6);
                                });
                              },
                            ),
                            children: [
                              TileLayer(
                                urlTemplate: _mapTileUrlTemplate(),
                                userAgentPackageName: 'cl.landfinder.desktop',
                              ),
                              MarkerLayer(
                                markers: [
                                  Marker(
                                    point: point,
                                    width: 44,
                                    height: 44,
                                    child: const Icon(
                                      Icons.location_on,
                                      color: Color(0xFF7C3AED),
                                      size: 36,
                                    ),
                                  ),
                                ],
                              ),
                            ],
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.of(context).pop(false),
                  child: const Text('Cancelar'),
                ),
                FilledButton.icon(
                  onPressed: lat == null || lon == null
                      ? null
                      : () => Navigator.of(context).pop(true),
                  icon: const Icon(Icons.check_circle_outline),
                  label: const Text('Confirmar ubicacion'),
                ),
              ],
            );
          },
        ),
      );
      if (assigned != true) {
        return;
      }
      await widget.api.assignPropertyLocation(
        property['internal_id'].toString(),
        {
          'latitude': _parseDouble(latController.text),
          'longitude': _parseDouble(lonController.text),
          'address': addressController.text.trim(),
          'region': regionController.text.trim(),
          'commune': communeController.text.trim(),
          'location_precision': 'EXACT',
        }..removeWhere((_, value) => value == null || value == ''),
      );
      await _refreshAll();
      final propertyId = property['internal_id']?.toString();
      if (propertyId != null) {
        await _loadTerritory(propertyId);
      }
      if (mounted) {
        setState(() => _section = AppSection.map);
      }
    } finally {
      addressController.dispose();
      regionController.dispose();
      communeController.dispose();
      latController.dispose();
      lonController.dispose();
    }
  }

  Future<void> _showDiagnostics(Map<String, dynamic> property) async {
    final propertyId = property['internal_id']?.toString();
    if (propertyId == null) {
      return;
    }
    try {
      final diagnostics = await widget.api.propertyDiagnostics(propertyId);
      if (!mounted) {
        return;
      }
      await showDialog<void>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Diagnostico'),
          content: SizedBox(
            width: 820,
            height: 620,
            child: SingleChildScrollView(
              child: SelectableText(
                const JsonEncoder.withIndent('  ').convert(diagnostics),
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Cerrar'),
            ),
          ],
        ),
      );
    } catch (error) {
      if (mounted) {
        setState(() => _error = error.toString());
      }
    }
  }

  Future<void> _loadAudit(String sourceId) async {
    setState(() {
      _audit = null;
      _error = null;
    });
    try {
      final audit = await widget.api.sourceAudit(sourceId);
      if (mounted) {
        setState(() => _audit = audit);
      }
    } catch (error) {
      if (mounted) {
        setState(() => _error = error.toString());
      }
    }
  }

  void _selectProperty(Map<String, dynamic> property) {
    setState(() {
      _selectedProperty = property;
      _selectedSourceRecord = null;
    });
    final propertyId = property['internal_id']?.toString();
    if (propertyId != null && !_territoryByProperty.containsKey(propertyId)) {
      unawaited(_loadTerritory(propertyId));
    }
  }

  Future<void> _loadTerritory(String propertyId) async {
    try {
      final territory = await widget.api.propertyTerritory(propertyId);
      if (mounted) {
        setState(() => _territoryByProperty[propertyId] = territory);
      }
    } catch (error) {
      if (mounted) {
        setState(() => _error = error.toString());
      }
    }
  }

  Future<void> _refreshSelectedTerritory({bool forceRefresh = true}) async {
    final property =
        _selectedProperty ??
        (_properties.isNotEmpty ? _properties.first : null);
    final propertyId = property?['internal_id']?.toString();
    if (propertyId == null || !_hasValidPropertyLocation(property!)) {
      return;
    }
    setState(() {
      _refreshingTerritory = true;
      _error = null;
    });
    try {
      final territory = await widget.api.evaluatePropertyTerritory(
        propertyId,
        forceRefresh: forceRefresh,
      );
      if (mounted) {
        setState(() => _territoryByProperty[propertyId] = territory);
      }
      await _refreshAll();
    } catch (error) {
      if (mounted) {
        setState(() => _error = error.toString());
      }
    } finally {
      if (mounted) {
        setState(() => _refreshingTerritory = false);
      }
    }
  }

  bool _isSecretConfigured(String key, String backendFlag) {
    return _secretStatus[key] == true || _settings[backendFlag] == true;
  }

  bool _isSourceConfigured(String sourceId) {
    return switch (sourceId) {
      'mercado_publico' => _isSecretConfigured(
        mercadoPublicoTicketKey,
        'has_mercado_publico_ticket',
      ),
      'mercadolibre_real_estate' => _isMercadoLibreConfigured,
      _ => true,
    };
  }

  bool _isEnrichmentConfigured(String sourceId) {
    return switch (sourceId) {
      'cmf_uf' => _isSecretConfigured(cmfApiKeyKey, 'has_cmf_api_key'),
      'minvu' => true,
      _ => false,
    };
  }

  bool get _isMercadoLibreConfigured {
    return _secretStatus[mercadoLibreAccessTokenKey] == true ||
        _secretStatus[mercadoLibreRefreshTokenKey] == true ||
        _settings['has_mercadolibre_access_token'] == true ||
        _settings['has_mercadolibre_refresh_token'] == true;
  }

  void _syncMercadoLibreCredentialFields() {
    final clientId = _settings['mercadolibre_client_id']?.toString();
    if (_mercadoLibreClientIdController.text.isEmpty &&
        clientId != null &&
        clientId.isNotEmpty) {
      _mercadoLibreClientIdController.text = clientId;
    }
    final redirectUri = _settings['mercadolibre_redirect_uri']?.toString();
    if (_mercadoLibreRedirectUriController.text.isEmpty &&
        redirectUri != null &&
        redirectUri.isNotEmpty) {
      _mercadoLibreRedirectUriController.text = redirectUri;
    }
    if (_mercadoLibreClientSecretController.text.isEmpty &&
        _settings['has_mercadolibre_client_secret'] == true) {
      _mercadoLibreClientSecretController.text = _maskedSecret;
    }
    final sellers = _settings['mercadolibre_partner_seller_ids']?.toString();
    if (_mercadoLibrePartnerSellersController.text.isEmpty &&
        sellers != null &&
        sellers.isNotEmpty) {
      _mercadoLibrePartnerSellersController.text = sellers;
    }
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final compact = constraints.maxWidth < 850;
        final content = _booting ? _buildBooting() : _buildContent();
        return Scaffold(
          body: SafeArea(
            child: compact
                ? Column(
                    children: [
                      Expanded(child: content),
                      NavigationBar(
                        selectedIndex: _section.index,
                        onDestinationSelected: (index) =>
                            setState(() => _section = AppSection.values[index]),
                        destinations: [
                          for (final section in AppSection.values.take(5))
                            NavigationDestination(
                              icon: Icon(section.icon),
                              label: section.label,
                            ),
                        ],
                      ),
                    ],
                  )
                : Row(
                    children: [
                      _SideRail(
                        selected: _section,
                        onSelected: (section) =>
                            setState(() => _section = section),
                      ),
                      Expanded(child: content),
                    ],
                  ),
          ),
        );
      },
    );
  }

  Widget _buildBooting() {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const SizedBox.square(
            dimension: 36,
            child: CircularProgressIndicator(strokeWidth: 3),
          ),
          const SizedBox(height: 16),
          Text(
            'Conectando backend local',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 6),
          Text('127.0.0.1:8765', style: Theme.of(context).textTheme.bodySmall),
        ],
      ),
    );
  }

  Widget _buildContent() {
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _Header(
            title: _section.label,
            subtitle: _subtitleForSection(),
            onRefresh: _refreshAll,
            actions: [
              FilledButton.icon(
                onPressed: _createManualProperty,
                icon: const Icon(Icons.add_location_alt_outlined),
                label: const Text('Agregar terreno'),
              ),
            ],
          ),
          if (_error != null) ...[
            const SizedBox(height: 12),
            _Banner(
              message: _error!,
              icon: Icons.error_outline,
              color: const Color(0xFFB91C1C),
            ),
          ],
          const SizedBox(height: 16),
          Expanded(child: _bodyForSection()),
        ],
      ),
    );
  }

  String _subtitleForSection() {
    return switch (_section) {
      AppSection.dashboard => 'MVP local con dos fuentes oficiales auditadas',
      AppSection.search => 'Filtros preliminares y progreso por etapas',
      AppSection.mercadoLibreImport => 'Importacion manual por API oficial',
      AppSection.results => 'Candidatos normalizados y persistidos',
      AppSection.map => 'Vista local de coordenadas disponibles',
      AppSection.sources => 'Estado operativo y auditoria por conector',
      AppSection.exports => 'Workbook Excel trazable',
      AppSection.settings => 'Fuentes y credenciales',
    };
  }

  Widget _bodyForSection() {
    return switch (_section) {
      AppSection.dashboard => _buildDashboard(),
      AppSection.search => _buildSearch(),
      AppSection.mercadoLibreImport => _buildMercadoLibreImport(),
      AppSection.results => _buildResults(),
      AppSection.map => _buildMap(),
      AppSection.sources => _buildSources(),
      AppSection.exports => _buildExports(),
      AppSection.settings => _buildSettings(),
    };
  }

  Widget _buildDashboard() {
    final activeSources = _sourceHealth
        .where((item) => item['status'] == 'ACTIVE')
        .length;
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: 12,
            runSpacing: 12,
            children: [
              _MetricTile(
                label: 'Terrenos',
                value: '${_properties.length}',
                icon: Icons.place_outlined,
              ),
              _MetricTile(
                label: 'Fuentes OK',
                value: '$activeSources/${_sources.length}',
                icon: Icons.hub_outlined,
              ),
              _MetricTile(
                label: 'Ultimo job',
                value: _job?['status']?.toString() ?? 'Sin job',
                icon: Icons.timeline_outlined,
              ),
              _MetricTile(
                label: 'Errores',
                value: _job?['error_count']?.toString() ?? '0',
                icon: Icons.warning_amber_outlined,
              ),
            ],
          ),
          const SizedBox(height: 18),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(child: _buildHealthPanel()),
              const SizedBox(width: 12),
              Expanded(child: _buildRecentEventsPanel()),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildHealthPanel() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const _PanelTitle(
              icon: Icons.monitor_heart_outlined,
              title: 'Fuentes',
            ),
            const SizedBox(height: 12),
            for (final item in _sourceHealth)
              _StatusRow(
                label: item['source_id']?.toString() ?? '',
                status: item['status']?.toString() ?? 'UNKNOWN',
                detail: _joinMessages(item['recent_errors']),
              ),
            if (_sourceHealth.isEmpty)
              const _EmptyLine(text: 'Sin fuentes cargadas'),
          ],
        ),
      ),
    );
  }

  Widget _buildRecentEventsPanel() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const _PanelTitle(
              icon: Icons.receipt_long_outlined,
              title: 'Eventos',
            ),
            const SizedBox(height: 12),
            for (final event in _events.reversed.take(8))
              _EventLine(event: event),
            if (_events.isEmpty)
              const _EmptyLine(text: 'Sin eventos recientes'),
          ],
        ),
      ),
    );
  }

  Widget _buildSearch() {
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SegmentedButton<bool>(
            segments: const [
              ButtonSegment(
                value: false,
                icon: Icon(Icons.sell_outlined),
                label: Text('Buscar ofertas'),
              ),
              ButtonSegment(
                value: true,
                icon: Icon(Icons.terrain_outlined),
                label: Text('Descubrir suelo'),
              ),
            ],
            selected: {_discoverSoilMode},
            onSelectionChanged: (value) {
              setState(() => _discoverSoilMode = value.first);
            },
          ),
          const SizedBox(height: 16),
          Wrap(
            spacing: 12,
            runSpacing: 12,
            children: [
              _buildRegionDropdown(),
              _buildCommuneSelector(),
              _InputBox(
                controller: _areaMinController,
                label: 'Sup. min m2',
                icon: Icons.square_foot_outlined,
              ),
              _InputBox(
                controller: _areaMaxController,
                label: 'Sup. max m2',
                icon: Icons.fit_screen_outlined,
              ),
              if (!_discoverSoilMode) ...[
                _InputBox(
                  controller: _priceMinController,
                  label: 'Precio min CLP',
                  icon: Icons.payments_outlined,
                ),
                _InputBox(
                  controller: _priceMaxController,
                  label: 'Precio max CLP',
                  icon: Icons.price_check_outlined,
                ),
              ],
            ],
          ),
          if (_discoverSoilMode) ...[
            const SizedBox(height: 12),
            CheckboxListTile(
              contentPadding: EdgeInsets.zero,
              value: _soilOnlyInsideUrbanLimit,
              onChanged: (value) {
                setState(() => _soilOnlyInsideUrbanLimit = value ?? false);
              },
              title: const Text('Solo dentro de limite urbano'),
              controlAffinity: ListTileControlAffinity.leading,
            ),
          ] else ...[
            const SizedBox(height: 16),
            _buildKeywordSelector(),
            const SizedBox(height: 16),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const _PanelTitle(
                      icon: Icons.hub_outlined,
                      title: 'Fuentes de busqueda',
                    ),
                    const SizedBox(height: 10),
                    for (final source in _sources)
                      _buildSearchSourceToggle(source),
                    const Divider(height: 24),
                    const _PanelTitle(
                      icon: Icons.analytics_outlined,
                      title: 'Servicios de analisis',
                    ),
                    const SizedBox(height: 10),
                    for (final source in _enrichmentSources)
                      _buildEnrichmentSourceToggle(source),
                    const _DisabledServiceRow(label: 'SII'),
                    const _DisabledServiceRow(label: 'DGA'),
                    const _DisabledServiceRow(label: 'CONAF'),
                  ],
                ),
              ),
            ),
          ],
          const SizedBox(height: 16),
          FilledButton.icon(
            onPressed: _searching || _discoveringSoil
                ? null
                : _discoverSoilMode
                ? _discoverSoil
                : _startSearch,
            icon: _searching || _discoveringSoil
                ? const SizedBox.square(
                    dimension: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.play_arrow_outlined),
            label: Text(
              _discoverSoilMode
                  ? (_discoveringSoil ? 'Buscando predios' : 'Buscar predios')
                  : (_searching ? 'Buscando' : 'Iniciar busqueda'),
            ),
          ),
          const SizedBox(height: 18),
          _buildJobPanel(),
        ],
      ),
    );
  }

  Widget _buildRegionDropdown() {
    final value =
        _regionsCatalog.any((item) => item['code'] == _selectedRegionCode)
        ? _selectedRegionCode
        : 'ALL';
    return SizedBox(
      width: 300,
      child: DropdownButtonFormField<String>(
        initialValue: value,
        isExpanded: true,
        decoration: const InputDecoration(
          border: OutlineInputBorder(
            borderRadius: BorderRadius.all(Radius.circular(8)),
          ),
          prefixIcon: Icon(Icons.public_outlined),
          labelText: 'Region',
          isDense: true,
        ),
        items: [
          const DropdownMenuItem(
            value: 'ALL',
            child: Text('Todas las regiones', overflow: TextOverflow.ellipsis),
          ),
          for (final region in _regionsCatalog)
            DropdownMenuItem(
              value: region['code']?.toString(),
              child: Text(
                region['name']?.toString() ?? '',
                overflow: TextOverflow.ellipsis,
              ),
            ),
        ],
        onChanged: (value) {
          if (value == null) {
            return;
          }
          setState(() {
            _selectedRegionCode = value;
            _selectedCommune = null;
            _validateSelectedResult();
          });
          unawaited(_loadCommunes(value));
        },
      ),
    );
  }

  Widget _buildCommuneSelector() {
    final catalogUnavailable = _communesCatalog.isEmpty;
    final addLabel = catalogUnavailable ? 'Cargar comunas' : 'Cambiar';
    return SizedBox(
      width: 300,
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: () => unawaited(_showCommunePicker()),
        child: InputDecorator(
          decoration: const InputDecoration(
            border: OutlineInputBorder(
              borderRadius: BorderRadius.all(Radius.circular(8)),
            ),
            prefixIcon: Icon(Icons.location_city_outlined),
            labelText: 'Comuna',
            isDense: true,
          ),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  _selectedCommuneSummary(),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              TextButton(
                onPressed: () => unawaited(_showCommunePicker()),
                child: Text(addLabel),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _showCommunePicker() async {
    if (_communesCatalog.isEmpty) {
      await _loadCommunes(_selectedRegionCode ?? 'ALL');
      if (!mounted) {
        return;
      }
    }
    Map<String, dynamic>? selected = _selectedCommune == null
        ? null
        : Map<String, dynamic>.from(_selectedCommune!);
    String query = '';
    String normalize(String value) => value
        .toLowerCase()
        .replaceAll(RegExp('[áàäâ]'), 'a')
        .replaceAll(RegExp('[éèëê]'), 'e')
        .replaceAll(RegExp('[íìïî]'), 'i')
        .replaceAll(RegExp('[óòöô]'), 'o')
        .replaceAll(RegExp('[úùüû]'), 'u')
        .replaceAll('ñ', 'n');
    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      barrierDismissible: true,
      builder: (context) {
        return StatefulBuilder(
          builder: (context, setDialogState) {
            final normalizedQuery = normalize(query.trim());
            final filtered = _communesCatalog.where((item) {
              if (normalizedQuery.isEmpty) {
                return true;
              }
              final haystack = normalize(
                [
                  item['name'],
                  item['region_name'],
                  item['region_code'],
                ].whereType<Object>().join(' '),
              );
              return haystack.contains(normalizedQuery);
            }).toList();
            return Dialog(
              child: ConstrainedBox(
                constraints: BoxConstraints(
                  maxWidth: 620,
                  maxHeight: MediaQuery.of(context).size.height * 0.75,
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Padding(
                      padding: const EdgeInsets.fromLTRB(20, 18, 20, 12),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const _PanelTitle(
                            icon: Icons.location_city_outlined,
                            title: 'Seleccionar comuna',
                          ),
                          const SizedBox(height: 12),
                          TextField(
                            autofocus: true,
                            decoration: const InputDecoration(
                              border: OutlineInputBorder(
                                borderRadius: BorderRadius.all(
                                  Radius.circular(8),
                                ),
                              ),
                              prefixIcon: Icon(Icons.search_outlined),
                              hintText: 'Buscar comuna o region',
                              isDense: true,
                            ),
                            onChanged: (value) {
                              setDialogState(() => query = value);
                            },
                          ),
                        ],
                      ),
                    ),
                    const Divider(height: 1),
                    Expanded(
                      child: filtered.isEmpty
                          ? const Center(
                              child: Text('No hay comunas para mostrar.'),
                            )
                          : ListView.builder(
                              padding: EdgeInsets.zero,
                              itemCount: filtered.length + 1,
                              itemBuilder: (context, index) {
                                if (index == 0) {
                                  return CheckboxListTile(
                                    dense: true,
                                    value: selected == null,
                                    onChanged: (_) {
                                      setDialogState(() => selected = null);
                                    },
                                    title: const Text('Todas las comunas'),
                                    subtitle: const Text('Sin filtro comunal'),
                                  );
                                }
                                final commune = filtered[index - 1];
                                final id =
                                    commune['commune_id']?.toString() ??
                                    commune['code']?.toString() ??
                                    '';
                                final name =
                                    commune['commune_name']?.toString() ??
                                    commune['name']?.toString() ??
                                    '';
                                final regionName = commune['region_name']
                                    ?.toString();
                                return CheckboxListTile(
                                  dense: true,
                                  value:
                                      selected?['commune_id']?.toString() == id,
                                  onChanged: (_) {
                                    setDialogState(() {
                                      selected = Map<String, dynamic>.from(
                                        commune,
                                      );
                                    });
                                  },
                                  title: Text(name),
                                  subtitle: regionName == null
                                      ? null
                                      : Text(regionName),
                                );
                              },
                            ),
                    ),
                    const Divider(height: 1),
                    Padding(
                      padding: const EdgeInsets.fromLTRB(12, 8, 12, 12),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.end,
                        children: [
                          TextButton(
                            onPressed: () {
                              setDialogState(() => selected = null);
                            },
                            child: const Text('Limpiar'),
                          ),
                          const SizedBox(width: 8),
                          TextButton(
                            onPressed: () => Navigator.of(context).pop(),
                            child: const Text('Cancelar'),
                          ),
                          const SizedBox(width: 8),
                          FilledButton(
                            onPressed: () {
                              Navigator.of(
                                context,
                              ).pop(selected ?? {'__all': true});
                            },
                            child: const Text('Aplicar'),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            );
          },
        );
      },
    );
    if (result != null && mounted) {
      setState(() {
        if (result['__all'] == true) {
          _applyCommuneChoice(null);
        } else {
          _applyCommuneChoice(result);
        }
      });
    }
  }

  Widget _buildKeywordSelector() {
    final activePreset = _keywordPresets.firstWhere(
      (item) => item['id'] == 'BUSQUEDA_TERRENOS_CHILE',
      orElse: () =>
          _keywordPresets.isEmpty ? <String, dynamic>{} : _keywordPresets.first,
    );
    final groups = List<Map<String, dynamic>>.from(
      (activePreset['groups'] as List? ?? const []).whereType<Map>().map(
        (item) => Map<String, dynamic>.from(item),
      ),
    );
    final exclusions = List<Object>.from(
      activePreset['exclusions'] as List? ?? const [],
    );
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Expanded(
                  child: _PanelTitle(
                    icon: Icons.search_outlined,
                    title: 'Busqueda inteligente',
                  ),
                ),
                Switch(value: true, onChanged: null),
              ],
            ),
            const SizedBox(height: 6),
            Text('Activada', style: Theme.of(context).textTheme.bodyMedium),
            const SizedBox(height: 12),
            SizedBox(
              width: 420,
              child: TextField(
                controller: _keywordAddController,
                decoration: InputDecoration(
                  border: const OutlineInputBorder(
                    borderRadius: BorderRadius.all(Radius.circular(8)),
                  ),
                  prefixIcon: const Icon(Icons.add_outlined),
                  labelText: 'Palabras adicionales (opcional)',
                  suffixIcon: IconButton(
                    tooltip: 'Agregar',
                    onPressed: _addKeyword,
                    icon: const Icon(Icons.check_outlined),
                  ),
                ),
                onSubmitted: (_) => _addKeyword(),
              ),
            ),
            if (_activeAdditionalKeywords().isNotEmpty) ...[
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final keyword in _activeAdditionalKeywords())
                    InputChip(
                      label: Text(keyword),
                      onDeleted: () {
                        setState(() => _keywordEnabled.remove(keyword));
                      },
                    ),
                ],
              ),
            ],
            const SizedBox(height: 8),
            ExpansionTile(
              tilePadding: EdgeInsets.zero,
              childrenPadding: EdgeInsets.zero,
              title: const Text('Configuracion avanzada'),
              children: [
                _DetailLine(
                  label: 'Preset activo',
                  value: _knownText(activePreset['name']),
                ),
                _DetailLine(
                  label: 'Terminos internos',
                  value: _activeKeywords().length.toString(),
                ),
                _DetailLine(label: 'Modo', value: _keywordMode),
                _DetailLine(
                  label: 'Grupos habilitados',
                  value: groups
                      .map((item) => '${item['id']} (${item['term_count']})')
                      .join(', '),
                ),
                _DetailLine(
                  label: 'Exclusiones',
                  value: exclusions.length.toString(),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSearchSourceToggle(Map<String, dynamic> source) {
    final sourceId = source['source_id'].toString();
    final configured = _isSourceConfigured(sourceId);
    final selected = _selectedSources.contains(sourceId);
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          Checkbox(
            value: selected,
            onChanged: (value) {
              setState(() {
                if (value == true) {
                  _selectedSources.add(sourceId);
                } else {
                  _selectedSources.remove(sourceId);
                }
              });
            },
          ),
          const SizedBox(width: 6),
          Icon(Icons.dataset_linked_outlined, size: 20),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(source['source_name']?.toString() ?? sourceId),
                Text(
                  configured ? 'Configurado' : 'No configurado',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
          ),
          if (!configured)
            OutlinedButton.icon(
              onPressed: () => setState(() => _section = AppSection.settings),
              icon: const Icon(Icons.settings_outlined),
              label: const Text('Configurar'),
            ),
        ],
      ),
    );
  }

  Widget _buildEnrichmentSourceToggle(Map<String, dynamic> source) {
    final sourceId = source['source_id'].toString();
    final configured = _isEnrichmentConfigured(sourceId);
    final selected = _selectedEnrichmentSources.contains(sourceId);
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          Checkbox(
            value: selected,
            onChanged: (value) {
              setState(() {
                if (value == true) {
                  _selectedEnrichmentSources.add(sourceId);
                } else {
                  _selectedEnrichmentSources.remove(sourceId);
                }
              });
            },
          ),
          const SizedBox(width: 6),
          Icon(
            sourceId == 'minvu'
                ? Icons.travel_explore_outlined
                : Icons.currency_exchange_outlined,
            size: 20,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(source['source_name']?.toString() ?? sourceId),
                Text(
                  configured ? 'Disponible' : 'No configurado',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
          ),
          if (!configured)
            OutlinedButton.icon(
              onPressed: () => setState(() => _section = AppSection.settings),
              icon: const Icon(Icons.settings_outlined),
              label: const Text('Configurar'),
            ),
        ],
      ),
    );
  }

  Widget _buildJobPanel() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const _PanelTitle(
                  icon: Icons.timeline_outlined,
                  title: 'Progreso',
                ),
                const Spacer(),
                if (_job != null)
                  _StatusChip(status: _job!['status']?.toString() ?? 'UNKNOWN'),
              ],
            ),
            const SizedBox(height: 12),
            if (_job != null)
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  _SmallStat(
                    label: 'Encontrados',
                    value: _job!['found_count']?.toString() ?? '0',
                  ),
                  _SmallStat(
                    label: 'Procesados',
                    value: _job!['processed_count']?.toString() ?? '0',
                  ),
                  _SmallStat(
                    label: 'Warnings',
                    value: _job!['warning_count']?.toString() ?? '0',
                  ),
                  _SmallStat(
                    label: 'Errores',
                    value: _job!['error_count']?.toString() ?? '0',
                  ),
                ],
              ),
            if (_job != null) ...[
              const SizedBox(height: 12),
              _buildSourceRunStatusPanel(),
            ],
            const SizedBox(height: 12),
            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 300),
              child: ListView.separated(
                shrinkWrap: true,
                itemCount: _events.length,
                separatorBuilder: (_, __) => const Divider(height: 1),
                itemBuilder: (context, index) =>
                    _EventLine(event: _events[index]),
              ),
            ),
            if (_events.isEmpty)
              const _EmptyLine(text: 'Sin busqueda ejecutada'),
          ],
        ),
      ),
    );
  }

  Widget _buildSourceRunStatusPanel() {
    final statuses = List<Map<String, dynamic>>.from(
      (_job?['source_run_status'] as List? ?? const []).whereType<Map>().map(
        (item) => Map<String, dynamic>.from(item),
      ),
    );
    if (statuses.isEmpty) {
      return const _EmptyLine(text: 'Sin estado por fuente');
    }
    return Column(
      children: [
        for (final row in statuses)
          _StatusRow(
            label: row['source_id']?.toString() ?? '',
            status: row['status']?.toString() ?? 'UNKNOWN',
            detail:
                'recibidos ${row['records_received'] ?? 0} | aceptados ${row['records_accepted'] ?? 0}',
          ),
      ],
    );
  }

  Widget _buildResults() {
    final sourceItems = _filteredSourceRecordItems();
    if (_properties.isEmpty && sourceItems.isEmpty) {
      return const _EmptyState(
        icon: Icons.table_rows_outlined,
        title: 'Sin resultados',
        message:
            'Configura credenciales y ejecuta una busqueda para llenar la auditoria.',
      );
    }
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          flex: 3,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _buildSourceRecordToolbar(),
              const SizedBox(height: 10),
              Expanded(
                child: Card(
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(8),
                    child: SingleChildScrollView(
                      scrollDirection: Axis.horizontal,
                      child: SingleChildScrollView(
                        child: DataTable(
                          showCheckboxColumn: false,
                          columns: const [
                            DataColumn(label: Text('Titulo')),
                            DataColumn(label: Text('Fuente')),
                            DataColumn(label: Text('Tipo')),
                            DataColumn(label: Text('Clasificacion')),
                            DataColumn(label: Text('Conf.')),
                            DataColumn(label: Text('Region terreno')),
                            DataColumn(label: Text('Comuna terreno')),
                            DataColumn(label: Text('Superficie')),
                            DataColumn(label: Text('Monto')),
                            DataColumn(label: Text('UF')),
                            DataColumn(label: Text('Fecha')),
                            DataColumn(label: Text('Organismo')),
                          ],
                          rows: [
                            for (final record in sourceItems)
                              _sourceRecordRow(record),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(width: 12),
        Expanded(child: _buildResultDetailPanel()),
      ],
    );
  }

  Widget _buildSourceRecordToolbar() {
    final distribution = _asMap(_sourceRecords?['classifier_distribution']);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                _bucketChip(
                  'candidates',
                  'Candidatos',
                  distribution['accepted'],
                ),
                _bucketChip('possible', 'Posibles', distribution['possible']),
                _bucketChip(
                  'rejected',
                  'Descartados',
                  distribution['rejected'],
                ),
                _bucketChip('all', 'Todos', distribution['total_analyzed']),
              ],
            ),
            const SizedBox(height: 10),
            SizedBox(
              width: 420,
              child: TextField(
                controller: _resultSearchController,
                decoration: const InputDecoration(
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.all(Radius.circular(8)),
                  ),
                  prefixIcon: Icon(Icons.search_outlined),
                  labelText: 'Buscar en estos resultados',
                  isDense: true,
                ),
                onChanged: (_) => setState(() {}),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _bucketChip(String bucket, String label, dynamic count) {
    final selected = _sourceRecordBucket == bucket;
    final countText = count == null ? '' : ' (${count.toString()})';
    return ChoiceChip(
      selected: selected,
      label: Text('$label$countText'),
      onSelected: (_) async {
        setState(() => _sourceRecordBucket = bucket);
        await _refreshSourceRecords();
      },
    );
  }

  DataRow _sourceRecordRow(Map<String, dynamic> record) {
    final property = _propertyForSourceRecord(record);
    final isCadastral = record['source'] == 'ciren_rural_properties' ||
        record['automatic_classification'] == 'CANDIDATO TERRITORIAL';
    final selected =
        _selectedSourceRecord?['source_record_id'] ==
        record['source_record_id'];
    return DataRow(
      selected: selected,
      onSelectChanged: (_) => _selectSourceRecord(record),
      cells: [
        DataCell(
          SizedBox(
            width: 280,
            child: Text(
              _knownText(record['title']),
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ),
        DataCell(Text(_knownText(record['source']))),
        DataCell(Text(_sourceTypeLabel(record['source_type']))),
        DataCell(
          Text(
            isCadastral
                ? 'CANDIDATO TERRITORIAL'
                : _knownText(record['automatic_classification']),
          ),
        ),
        DataCell(Text(_confidenceText(record['automatic_confidence']))),
        DataCell(
          Text(_knownText(record['property_region'] ?? record['region'])),
        ),
        DataCell(
          Text(_knownText(record['property_commune'] ?? record['commune'])),
        ),
        DataCell(Text(_knownNumber(record['surface_m2'], suffix: ' m2'))),
        DataCell(Text(isCadastral ? '-' : _amountText(record))),
        DataCell(Text(isCadastral ? '-' : _knownNumber(property?['asking_price_uf']))),
        DataCell(Text(_knownText(record['publication_date']))),
        DataCell(
          SizedBox(
            width: 220,
            child: Text(
              isCadastral ? 'CIREN' : _knownText(record['organization']),
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ),
      ],
    );
  }

  List<Map<String, dynamic>> _filteredSourceRecordItems() {
    final items = List<Map<String, dynamic>>.from(
      (_sourceRecords?['items'] as List? ?? const []).whereType<Map>().map(
        (item) => Map<String, dynamic>.from(item),
      ),
    );
    final query = _resultSearchController.text.trim().toLowerCase();
    if (query.isEmpty) {
      return items;
    }
    return [
      for (final item in items)
        if ([
          item['title'],
          item['description'],
          item['organization'],
          item['property_commune'],
          item['commune'],
          item['positive_terms'],
        ].any((value) => value.toString().toLowerCase().contains(query)))
          item,
    ];
  }

  void _selectSourceRecord(Map<String, dynamic> record) {
    final property = _propertyForSourceRecord(record);
    setState(() {
      _selectedSourceRecord = record;
      if (property != null) {
        _selectedProperty = property;
      }
    });
    final propertyId = property?['internal_id']?.toString();
    if (propertyId != null && !_territoryByProperty.containsKey(propertyId)) {
      unawaited(_loadTerritory(propertyId));
    }
  }

  Map<String, dynamic>? _propertyForSourceRecord(Map<String, dynamic> record) {
    final propertyId = record['property_id']?.toString();
    if (propertyId == null || propertyId.isEmpty) {
      return null;
    }
    for (final property in _properties) {
      if (property['internal_id']?.toString() == propertyId) {
        return property;
      }
    }
    return null;
  }

  Widget _buildResultDetailPanel() {
    _validateSelectedResult();
    final record = _selectedSourceRecord;
    if (record != null) {
      final property = _propertyForSourceRecord(record);
      return Card(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const _PanelTitle(
                icon: Icons.fact_check_outlined,
                title: 'Registro fuente',
              ),
              const SizedBox(height: 12),
              Text(
                _knownText(record['title']),
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 12),
              _DetailLine(
                label: 'ID fuente',
                value: _knownText(record['external_id']),
              ),
              _DetailLine(
                label: 'Clasificacion automatica',
                value: _knownText(record['automatic_classification']),
              ),
              _DetailLine(
                label: 'Confianza',
                value: _confidenceText(record['automatic_confidence']),
              ),
              _DetailLine(
                label: 'Revision manual',
                value: _knownText(record['manual_classification']),
              ),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  OutlinedButton.icon(
                    onPressed: () =>
                        _updateManualClassification(record, 'CONFIRMED_LAND'),
                    icon: const Icon(Icons.check_circle_outline),
                    label: const Text('Es terreno'),
                  ),
                  OutlinedButton.icon(
                    onPressed: () =>
                        _updateManualClassification(record, 'POSSIBLE_LAND'),
                    icon: const Icon(Icons.help_outline),
                    label: const Text('Posible'),
                  ),
                  OutlinedButton.icon(
                    onPressed: () => _updateManualClassification(
                      record,
                      'CONFIRMED_NOT_LAND',
                    ),
                    icon: const Icon(Icons.block_outlined),
                    label: const Text('No es terreno'),
                  ),
                ],
              ),
              const Divider(height: 24),
              const _MiniSectionTitle('Fuente'),
              _DetailLine(
                label: 'Organismo',
                value: _knownText(record['organization']),
              ),
              _DetailLine(
                label: 'Region organismo',
                value: _knownText(record['organization_region']),
              ),
              _DetailLine(
                label: 'Comuna organismo',
                value: _knownText(record['organization_commune']),
              ),
              _DetailLine(
                label: 'Direccion organismo',
                value: _knownText(record['organization_address']),
              ),
              const _MiniSectionTitle('Predio extraido'),
              _DetailLine(
                label: 'Region terreno',
                value: _knownText(
                  record['property_region'] ?? record['region'],
                ),
              ),
              _DetailLine(
                label: 'Comuna terreno',
                value: _knownText(
                  record['property_commune'] ?? record['commune'],
                ),
              ),
              _DetailLine(
                label: 'Direccion terreno',
                value: _knownText(record['property_address']),
              ),
              _DetailLine(
                label: 'Superficie',
                value: _knownNumber(record['surface_m2'], suffix: ' m2'),
              ),
              _DetailLine(label: 'Monto', value: _amountText(record)),
              _DetailLine(
                label: 'Tipo monto',
                value: _knownText(record['amount_type']),
              ),
              const _MiniSectionTitle('Extraction Diagnostics'),
              _DetailLine(
                label: 'Detail fetched',
                value: _yesNoText(record['detail_fetched']),
              ),
              _DetailLine(
                label: 'Detail attempts',
                value: _knownText(record['detail_attempts']),
              ),
              _DetailLine(
                label: 'HTTP status',
                value: _knownText(record['detail_http_status']),
              ),
              _DetailLine(
                label: 'Campos extraidos',
                value: _joinList(record['fields_extracted']),
              ),
              _DetailLine(
                label: 'Campos faltantes',
                value: _joinList(record['fields_missing']),
              ),
              _DetailLine(
                label: 'Razones',
                value: _evidenceValueText(record['extraction_reasons']),
              ),
              _DetailLine(
                label: 'Calidad datos',
                value: _knownText(record['data_completeness_score']),
              ),
              if (_sourceUrlFromRecord(record) != null) ...[
                const SizedBox(height: 8),
                OutlinedButton.icon(
                  onPressed: () => _openUrl(_sourceUrlFromRecord(record)!),
                  icon: const Icon(Icons.open_in_new_outlined),
                  label: const Text('Abrir Mercado Publico'),
                ),
              ],
              if (property != null) ...[
                const Divider(height: 24),
                FilledButton.icon(
                  onPressed: () => _showFullPropertyDetail(property),
                  icon: const Icon(Icons.open_in_full_outlined),
                  label: const Text('Ver detalle completo'),
                ),
              ],
            ],
          ),
        ),
      );
    }
    final property = _selectedProperty;
    if (property != null &&
        _visiblePropertyIds().contains(property['internal_id']?.toString())) {
      return _buildPropertyDetail(allowFallback: false);
    }
    return const Card(
      child: Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Text('Selecciona una fila visible para ver el detalle.'),
        ),
      ),
    );
  }

  Widget _buildPropertyDetail({bool allowFallback = true}) {
    final property =
        _selectedProperty ??
        (allowFallback && _properties.isNotEmpty ? _properties.first : null);
    if (property == null) {
      return const SizedBox.shrink();
    }
    return Card(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const _PanelTitle(icon: Icons.article_outlined, title: 'Detalle'),
            const SizedBox(height: 12),
            Text(
              _knownText(property['publication_title']),
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 12),
            _DetailLine(
              label: 'ID',
              value: _knownText(property['internal_id']),
            ),
            _DetailLine(label: 'Fuente', value: _knownText(property['source'])),
            _DetailLine(label: 'Region', value: _knownText(property['region'])),
            _DetailLine(
              label: 'Comuna',
              value: _knownText(property['commune']),
            ),
            _DetailLine(
              label: 'Direccion',
              value: _knownText(
                property['normalized_address'] ?? property['original_address'],
              ),
            ),
            _DetailLine(
              label: 'URL',
              value: _knownText(property['canonical_url']),
            ),
            _DetailLine(
              label: 'Monto CLP',
              value: _knownNumber(property['asking_price_clp']),
            ),
            _DetailLine(
              label: 'Monto equivalente UF',
              value: _knownNumber(property['asking_price_uf']),
            ),
            _DetailLine(
              label: 'UF rate',
              value: _knownNumber(property['uf_rate']),
            ),
            _DetailLine(
              label: 'Fecha UF',
              value: _knownText(property['uf_rate_date']),
            ),
            _DetailLine(
              label: 'Observaciones',
              value: _knownText(property['anomaly_flags_json']),
            ),
            Align(
              alignment: Alignment.centerLeft,
              child: Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  OutlinedButton.icon(
                    onPressed: () => _showFullPropertyDetail(property),
                    icon: const Icon(Icons.open_in_full_outlined),
                    label: const Text('Ver detalle completo'),
                  ),
                  OutlinedButton.icon(
                    onPressed: () => _showAssignLocationDialog(property),
                    icon: const Icon(Icons.add_location_alt_outlined),
                    label: const Text('Asignar ubicacion'),
                  ),
                  OutlinedButton.icon(
                    onPressed: () => _showDiagnostics(property),
                    icon: const Icon(Icons.rule_folder_outlined),
                    label: const Text('Diagnostico'),
                  ),
                ],
              ),
            ),
            const Divider(height: 24),
            Row(
              children: [
                const Expanded(
                  child: _PanelTitle(
                    icon: Icons.public_outlined,
                    title: 'Territorio',
                  ),
                ),
                IconButton.filledTonal(
                  tooltip: 'Evaluar territorialmente',
                  onPressed:
                      _refreshingTerritory ||
                          !_hasValidPropertyLocation(property)
                      ? null
                      : () => _refreshSelectedTerritory(forceRefresh: true),
                  icon: _refreshingTerritory
                      ? const SizedBox.square(
                          dimension: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.travel_explore_outlined),
                ),
              ],
            ),
            const SizedBox(height: 12),
            if (!_hasValidPropertyLocation(property))
              const _EmptyLine(text: 'Analisis pendiente: falta geometria o ubicacion.'),
            else
              const SizedBox.shrink(),
            _buildTerritorySection(property),
          ],
        ),
      ),
    );
  }

  Widget _buildTerritorySection(Map<String, dynamic> property) {
    final propertyId = property['internal_id']?.toString();
    final territory = propertyId == null
        ? null
        : _territoryByProperty[propertyId];
    final metrics = _asMap(territory?['geometry_metrics']);
    final urban = _asMap(territory?['urban_limit']);
    final risk = _asMap(territory?['risk_intersection']);
    final prc = _asMap(territory?['prc']);
    final assessment = _asMap(territory?['preliminary_assessment']);
    final mma = _asMap(assessment['mma']);
    final dga = _asMap(assessment['dga']);
    final mop = _asMap(assessment['mop']);
    final evidence = List<Map<String, dynamic>>.from(
      (territory?['evidence'] as List? ?? const []).whereType<Map>().map(
        (item) => Map<String, dynamic>.from(item),
      ),
    );
    final territoryProperty = _asMap(territory?['property']);
    final adminValidation = _asMap(territory?['admin_validation'] ?? property);
    final provenance = List<Map<String, dynamic>>.from(
      ((territory?['data_provenance'] ?? territoryProperty['data_provenance'])
                  as List? ??
              const [])
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item)),
    );
    final urbanEvidence = _latestEvidence(evidence, 'inside_urban_limit');
    final riskEvidence = _latestEvidence(evidence, 'risk_intersection');
    final prcEvidence = _latestEvidence(evidence, 'prc_applicable');
    final urbanStatus =
        urban['status'] ??
        _decodeMaybeJson(urbanEvidence?['value']) ??
        'No verificado';
    final riskValue = risk.isNotEmpty
        ? risk
        : _asMap(_decodeMaybeJson(riskEvidence?['value']));
    final riskTypes = _joinList(riskValue['risk_types']);
    final latitude = _asDouble(property['latitude']);
    final longitude = _asDouble(property['longitude']);
    final coords = latitude == null || longitude == null
        ? 'Sin informacion'
        : '${latitude.toStringAsFixed(6)}, ${longitude.toStringAsFixed(6)}';
    final dimensions = _dimensionsText(metrics);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _MiniSectionTitle('Ubicacion'),
        _DetailLine(label: 'Region', value: _knownText(property['region'])),
        _DetailLine(label: 'Comuna', value: _knownText(property['commune'])),
        _DetailLine(label: 'Coordenadas', value: coords),
        _DetailLine(
          label: 'Precision',
          value: _knownText(
            property['location_precision'] ?? metrics['geometry_status'],
          ),
        ),
        _MiniSectionTitle('Validacion de ubicacion'),
        _buildAdminValidationSection(adminValidation),
        _MiniSectionTitle('Predio'),
        _DetailLine(
          label: 'Superficie publicada',
          value: _knownNumber(
            property['advertised_area_m2'] ?? property['gross_area_m2'],
            suffix: ' m2',
          ),
        ),
        _DetailLine(
          label: 'Superficie GIS',
          value: _knownNumber(metrics['geometric_area_m2'], suffix: ' m2'),
        ),
        _DetailLine(
          label: 'Diferencia',
          value: _knownNumber(metrics['area_difference_percent'], suffix: '%'),
        ),
        _DetailLine(
          label: 'Perimetro',
          value: _knownNumber(metrics['perimeter_m'], suffix: ' m'),
        ),
        _DetailLine(label: 'Dimensiones aproximadas', value: dimensions),
        _DetailLine(label: 'Forma', value: _shapeText(metrics)),
        _MiniSectionTitle('Urbanismo'),
        _DetailLine(
          label: 'Dentro limite urbano',
          value: _urbanLimitLabel(urbanStatus),
        ),
        _DetailLine(
          label: 'PRC encontrado',
          value: _knownText(prc['applicable_service'] ?? prcEvidence?['value']),
        ),
        _DetailLine(label: 'Zona encontrada', value: _knownText(prc['zone'])),
        _MiniSectionTitle('Riesgos'),
        _DetailLine(
          label: 'Intersecciones detectadas',
          value: _riskStatusLabel(riskValue['status']),
        ),
        _DetailLine(
          label: 'Tipos',
          value: riskTypes.isEmpty ? 'Sin informacion' : riskTypes,
        ),
        _DetailLine(
          label: 'Fuente',
          value: _knownText(
            riskValue['source'] ?? riskEvidence?['source_name'],
          ),
        ),
        _DetailLine(
          label: 'Fecha',
          value: _knownText(
            riskValue['retrieved_at'] ?? riskEvidence?['retrieved_at'],
          ),
        ),
        _DetailLine(
          label: 'Precision',
          value: _knownText(riskValue['analysis_precision']),
        ),
        _MiniSectionTitle('Ambiente'),
        _DetailLine(
          label: 'Area protegida',
          value: _knownText(mma['protected_area']),
        ),
        _DetailLine(label: 'Humedal', value: _knownText(mma['wetland'])),
        _MiniSectionTitle('Agua'),
        _DetailLine(
          label: 'Restriccion DGA',
          value: _knownText(dga['restriction']),
        ),
        _DetailLine(
          label: 'Derechos cercanos',
          value: _knownText(dga['water_rights_nearby']),
        ),
        _MiniSectionTitle('Accesibilidad'),
        _DetailLine(
          label: 'Via MOP mas cercana',
          value: _knownNumber(mop['distance_to_mop_road_m'], suffix: ' m'),
        ),
        const _EmptyLine(
          text: 'Distancia territorial; no acredita acceso juridico o servidumbre.',
        ),
        _MiniSectionTitle('Resultado preliminar'),
        _DetailLine(
          label: 'Estado',
          value: _knownText(
            assessment['status'] ?? property['territorial_status'],
          ),
        ),
        const _EmptyLine(
          text:
              'Esta evaluacion es preliminar y no reemplaza certificados, permisos ni analisis normativo oficial.',
        ),
        _MiniSectionTitle('Procedencia de informacion'),
        _buildProvenanceSection(provenance),
        _MiniSectionTitle('Fuentes y evidencia'),
        Align(
          alignment: Alignment.centerLeft,
          child: OutlinedButton.icon(
            onPressed: evidence.isEmpty
                ? null
                : () => _showEvidenceDialog(evidence),
            icon: const Icon(Icons.fact_check_outlined),
            label: const Text('Ver evidencia'),
          ),
        ),
        const SizedBox(height: 8),
        _buildEvidenceSection(evidence),
      ],
    );
  }

  Widget _buildAdminValidationSection(Map<String, dynamic> validation) {
    final status = _knownText(validation['admin_validation_status']);
    final isConflict = {
      'COMMUNE_MISMATCH',
      'REGION_MISMATCH',
      'COMMUNE_AND_REGION_MISMATCH',
      'OUTSIDE_CHILE',
      'GEOMETRY_INVALID',
    }.contains(status.toUpperCase());
    final icon = isConflict
        ? Icons.warning_amber_outlined
        : Icons.check_circle_outline;
    final color = isConflict ? Colors.orange.shade800 : Colors.green.shade700;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(icon, color: color, size: 18),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                isConflict
                    ? 'Conflicto de ubicacion'
                    : _adminStatusLabel(status),
                style: TextStyle(color: color, fontWeight: FontWeight.w600),
              ),
            ),
          ],
        ),
        _DetailLine(
          label: 'Fuente',
          value:
              '${_knownText(validation['source_commune'])}, ${_knownText(validation['source_region'])}',
        ),
        _DetailLine(
          label: 'Geometria',
          value:
              '${_knownText(validation['calculated_commune'])}, ${_knownText(validation['calculated_region'])}',
        ),
        _DetailLine(
          label: 'CRS',
          value:
              '${_knownText(validation['source_epsg'])} -> ${_knownText(validation['normalized_epsg'])}',
        ),
        if (isConflict)
          const _EmptyLine(
            text: 'Analisis territorial bloqueado hasta revisar ubicacion.',
          )
        else
          _DetailLine(
            label: 'Motivo',
            value: _knownText(validation['admin_validation_reason']),
          ),
      ],
    );
  }

  Widget _buildProvenanceSection(List<Map<String, dynamic>> provenance) {
    if (provenance.isEmpty) {
      return const _EmptyLine(text: 'Sin informacion');
    }
    final visible = <String, Map<String, dynamic>>{};
    for (final item in provenance) {
      final field = item['field_name']?.toString() ?? '';
      if (field.isEmpty) {
        continue;
      }
      visible.putIfAbsent(field, () => item);
    }
    final fields = [
      'asking_price_clp',
      'asking_price_uf',
      'uf_rate',
      'price_uf_m2_gross',
      'inside_urban_limit',
      'prc_applicable',
      'urban_zone',
      'risk_intersection',
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final field in fields)
          if (visible.containsKey(field))
            _DetailLine(
              label: _provenanceLabel(field),
              value: _knownText(
                visible[field]?['source_id'] ?? visible[field]?['source'],
              ),
            ),
      ],
    );
  }

  void _showEvidenceDialog(List<Map<String, dynamic>> evidence) {
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Fuentes y evidencia'),
        content: SizedBox(
          width: 720,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                for (final record in evidence)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: _EvidenceRecordTile(
                      evidence: record,
                      onOpenSource: () => _openEvidenceSource(record),
                    ),
                  ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cerrar'),
          ),
        ],
      ),
    );
  }

  Widget _buildEvidenceSection(List<Map<String, dynamic>> evidence) {
    if (evidence.isEmpty) {
      return const _EmptyLine(text: 'No verificado');
    }
    return Column(
      children: [
        for (final record in evidence.take(10))
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: _EvidenceRecordTile(
              evidence: record,
              onOpenSource: () => _openEvidenceSource(record),
            ),
          ),
      ],
    );
  }

  void _showFullPropertyDetail(Map<String, dynamic> property) {
    final record = _selectedSourceRecord;
    final propertyId = property['internal_id']?.toString();
    final territory = propertyId == null
        ? null
        : _territoryByProperty[propertyId];
    final evidence = List<Map<String, dynamic>>.from(
      (territory?['evidence'] as List? ?? const []).whereType<Map>().map(
        (item) => Map<String, dynamic>.from(item),
      ),
    );
    showDialog<void>(
      context: context,
      builder: (context) => Dialog.fullscreen(
        child: DefaultTabController(
          length: 6,
          child: Scaffold(
            appBar: AppBar(
              title: Text(_knownText(property['publication_title'])),
              bottom: const TabBar(
                isScrollable: true,
                tabs: [
                  Tab(text: 'Resumen'),
                  Tab(text: 'Fuente'),
                  Tab(text: 'Clasificacion'),
                  Tab(text: 'Territorio'),
                  Tab(text: 'Evidencia'),
                  Tab(text: 'Datos crudos'),
                ],
              ),
            ),
            body: TabBarView(
              children: [
                _FullDetailTab(
                  children: [
                    _DetailLine(label: 'ID', value: _knownText(propertyId)),
                    _DetailLine(
                      label: 'Fuente',
                      value: _knownText(property['source']),
                    ),
                    _DetailLine(
                      label: 'Region',
                      value: _knownText(property['region']),
                    ),
                    _DetailLine(
                      label: 'Comuna',
                      value: _knownText(property['commune']),
                    ),
                    _DetailLine(
                      label: 'Superficie',
                      value: _knownNumber(
                        property['gross_area_m2'],
                        suffix: ' m2',
                      ),
                    ),
                    _DetailLine(
                      label: 'Monto CLP',
                      value: _knownNumber(property['asking_price_clp']),
                    ),
                    _DetailLine(
                      label: 'Monto equivalente UF',
                      value: _knownNumber(property['asking_price_uf']),
                    ),
                  ],
                ),
                _FullDetailTab(
                  children: [
                    _DetailLine(
                      label: 'SourceRecord',
                      value: _knownText(record?['source_record_id']),
                    ),
                    _DetailLine(
                      label: 'External ID',
                      value: _knownText(record?['external_id']),
                    ),
                    _DetailLine(
                      label: 'Organismo',
                      value: _knownText(record?['organization']),
                    ),
                    _DetailLine(
                      label: 'Direccion organismo',
                      value: _knownText(record?['organization_address']),
                    ),
                    _DetailLine(
                      label: 'URL',
                      value: _knownText(record?['source_url']),
                    ),
                  ],
                ),
                _FullDetailTab(
                  children: [
                    _DetailLine(
                      label: 'Automatica',
                      value: _knownText(record?['automatic_classification']),
                    ),
                    _DetailLine(
                      label: 'Confianza',
                      value: _confidenceText(record?['automatic_confidence']),
                    ),
                    _DetailLine(
                      label: 'Score',
                      value: _knownText(record?['automatic_score']),
                    ),
                    _DetailLine(
                      label: 'Positivos',
                      value: _joinList(record?['positive_terms']),
                    ),
                    _DetailLine(
                      label: 'Negativos',
                      value: _joinList(record?['negative_terms']),
                    ),
                    _DetailLine(
                      label: 'Reglas',
                      value: _joinList(record?['rules_triggered']),
                    ),
                    _DetailLine(
                      label: 'Manual',
                      value: _knownText(record?['manual_classification']),
                    ),
                  ],
                ),
                SingleChildScrollView(
                  padding: const EdgeInsets.all(20),
                  child: _buildTerritorySection(property),
                ),
                _FullDetailTab(
                  children: [
                    if (evidence.isEmpty)
                      const _EmptyLine(text: 'No verificado')
                    else
                      for (final item in evidence)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 8),
                          child: _EvidenceRecordTile(
                            evidence: item,
                            onOpenSource: () => _openEvidenceSource(item),
                          ),
                        ),
                  ],
                ),
                _FullDetailTab(
                  children: [
                    _DetailLine(
                      label: 'Property raw',
                      value: jsonEncode(property),
                    ),
                    _DetailLine(
                      label: 'Source raw',
                      value: jsonEncode(record?['raw_payload'] ?? {}),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _openEvidenceSource(Map<String, dynamic> evidence) async {
    final url = _sourceUrl(evidence);
    if (url == null) {
      return;
    }
    await _openUrl(url);
  }

  Future<void> _openUrl(String url) async {
    final uri = Uri.tryParse(url);
    if (uri == null) {
      return;
    }
    await launchUrl(uri, mode: LaunchMode.externalApplication);
  }

  Widget _buildMap() {
    final visibleProperties = _mapVisibleProperties();
    Map<String, dynamic>? selected = _selectedProperty;
    if (selected != null &&
        !visibleProperties.any(
          (property) =>
              property['internal_id']?.toString() ==
              selected?['internal_id']?.toString(),
        )) {
      selected = null;
    }
    if (selected == null) {
      for (final property in visibleProperties) {
        if (_hasValidPropertyLocation(property)) {
          selected = property;
          break;
        }
      }
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            FilterChip(
              selected: _showPotentialStatus,
              label: const Text('Potencialmente aptos'),
              onSelected: (value) =>
                  setState(() => _showPotentialStatus = value),
            ),
            FilterChip(
              selected: _showReviewStatus,
              label: const Text('Requieren revision'),
              onSelected: (value) => setState(() => _showReviewStatus = value),
            ),
            FilterChip(
              selected: _showUnsuitableStatus,
              label: const Text('Potencialmente no aptos'),
              onSelected: (value) =>
                  setState(() => _showUnsuitableStatus = value),
            ),
            FilterChip(
              selected: _showInsufficientStatus,
              label: const Text('Sin informacion'),
              onSelected: (value) =>
                  setState(() => _showInsufficientStatus = value),
            ),
          ],
        ),
        const SizedBox(height: 12),
        Expanded(
          child: LandfinderMapScreen(
            properties: visibleProperties,
            selectedProperty: selected,
            territoryByProperty: _territoryByProperty,
            showLandLayer: _showLandLayer,
            showUrbanLimitLayer: _showUrbanLimitLayer,
            showRiskLayer: _showRiskLayer,
            showZoningLayer: _showZoningLayer,
            refreshingTerritory: _refreshingTerritory,
            tileUrlTemplate: _mapTileUrlTemplate(),
            tileAttributionUrl: _mapAttributionUrl(),
            onLandLayerChanged: (value) =>
                setState(() => _showLandLayer = value),
            onUrbanLimitLayerChanged: (value) =>
                setState(() => _showUrbanLimitLayer = value),
            onRiskLayerChanged: (value) =>
                setState(() => _showRiskLayer = value),
            onZoningLayerChanged: (value) =>
                setState(() => _showZoningLayer = value),
            onSelectProperty: _selectProperty,
            onRefreshTerritory: () =>
                _refreshSelectedTerritory(forceRefresh: false),
            onViewTerritory: (property) {
              _selectProperty(property);
              setState(() => _section = AppSection.results);
            },
          ),
        ),
      ],
    );
  }

  List<Map<String, dynamic>> _mapVisibleProperties() {
    return [
      for (final property in _properties)
        if (_isVisibleMapStatus(property)) property,
    ];
  }

  bool _isVisibleMapStatus(Map<String, dynamic> property) {
    final status = property['territorial_status']?.toString().toUpperCase();
    if (status == 'POTENCIALMENTE_APTO') {
      return _showPotentialStatus;
    }
    if (status == 'REQUIERE_REVISION') {
      return _showReviewStatus;
    }
    if (status == 'POTENCIALMENTE_NO_APTO') {
      return _showUnsuitableStatus;
    }
    return _showInsufficientStatus;
  }

  String _mapTileUrlTemplate() {
    final provider = _selectedMapProvider();
    return provider?['tile_url_template']?.toString() ??
        'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
  }

  String _mapAttributionUrl() {
    final provider = _selectedMapProvider();
    return provider?['attribution_url']?.toString() ??
        'https://www.openstreetmap.org/copyright';
  }

  Map<String, dynamic>? _selectedMapProvider() {
    final selected = _mapProviders['selected']?.toString();
    final items = _mapProviders['items'];
    if (items is! List) {
      return null;
    }
    for (final item in items.whereType<Map>()) {
      if (item['provider_id']?.toString() == selected &&
          item['tile_url_template'] != null) {
        return Map<String, dynamic>.from(item);
      }
    }
    for (final item in items.whereType<Map>()) {
      if (item['provider_id']?.toString() == 'osm') {
        return Map<String, dynamic>.from(item);
      }
    }
    return null;
  }

  Widget _buildSources() {
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final source in _sources)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Row(
                    children: [
                      Icon(
                        AppSection.sources.icon,
                        color: Theme.of(context).colorScheme.primary,
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              source['source_name']?.toString() ?? '',
                              style: Theme.of(context).textTheme.titleMedium,
                            ),
                            const SizedBox(height: 4),
                            Text(
                              source['strategy']?.toString() ?? '',
                              style: Theme.of(context).textTheme.bodySmall,
                            ),
                          ],
                        ),
                      ),
                      _StatusChip(
                        status:
                            _healthFor(
                              source['source_id'].toString(),
                            )?['status']?.toString() ??
                            'UNKNOWN',
                      ),
                      const SizedBox(width: 8),
                      OutlinedButton.icon(
                        onPressed: () =>
                            _loadAudit(source['source_id'].toString()),
                        icon: const Icon(Icons.fact_check_outlined),
                        label: const Text('Auditar'),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          if (_audit != null) _AuditPanel(audit: _audit!),
        ],
      ),
    );
  }

  Widget _buildMercadoLibreImport() {
    final preview = _mercadoLibreImportPreview;
    final items = List<Map<String, dynamic>>.from(
      preview?['items'] as List? ?? const [],
    );
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const _PanelTitle(
                    icon: Icons.add_link_outlined,
                    title: 'Importar publicaciones Mercado Libre',
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Pega URLs o IDs de publicaciones de Mercado Libre/PortalInmobiliario. Landfinder extraera los IDs, consultara la API oficial y agregara los terrenos validos.',
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: _mercadoLibreImportController,
                    minLines: 8,
                    maxLines: 12,
                    decoration: const InputDecoration(
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.all(Radius.circular(8)),
                      ),
                      labelText: 'URLs o IDs MLC',
                      alignLabelWithHint: true,
                    ),
                  ),
                  const SizedBox(height: 12),
                  Wrap(
                    spacing: 10,
                    runSpacing: 8,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      FilterChip(
                        selected: _importVacantLand,
                        label: const Text('VACANT_LAND'),
                        onSelected: (value) =>
                            setState(() => _importVacantLand = value),
                      ),
                      FilterChip(
                        selected: _importLandWithStructure,
                        label: const Text('LAND_WITH_STRUCTURE'),
                        onSelected: (value) =>
                            setState(() => _importLandWithStructure = value),
                      ),
                      FilterChip(
                        selected: _importUnknownLand,
                        label: const Text('UNKNOWN'),
                        onSelected: (value) =>
                            setState(() => _importUnknownLand = value),
                      ),
                      FilterChip(
                        selected: _importNonLandProperty,
                        label: const Text('NON_LAND_PROPERTY'),
                        onSelected: (value) =>
                            setState(() => _importNonLandProperty = value),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Wrap(
                    spacing: 10,
                    runSpacing: 10,
                    children: [
                      FilledButton.icon(
                        onPressed: _analyzingMercadoLibreImport
                            ? null
                            : _analyzeMercadoLibreImport,
                        icon: _analyzingMercadoLibreImport
                            ? const SizedBox.square(
                                dimension: 18,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                ),
                              )
                            : const Icon(Icons.manage_search_outlined),
                        label: Text(
                          _analyzingMercadoLibreImport
                              ? 'Analizando'
                              : 'Analizar',
                        ),
                      ),
                      OutlinedButton.icon(
                        onPressed: _importingMercadoLibreItems
                            ? null
                            : _importMercadoLibreItems,
                        icon: _importingMercadoLibreItems
                            ? const SizedBox.square(
                                dimension: 18,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                ),
                              )
                            : const Icon(Icons.file_upload_outlined),
                        label: Text(
                          _importingMercadoLibreItems
                              ? 'Importando'
                              : 'Importar validos',
                        ),
                      ),
                      TextButton.icon(
                        onPressed: _clearMercadoLibreImport,
                        icon: const Icon(Icons.clear_outlined),
                        label: const Text('Limpiar'),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
          if (preview != null) ...[
            const SizedBox(height: 12),
            _MercadoLibreImportSummary(preview: preview),
          ],
          if (items.isNotEmpty) ...[
            const SizedBox(height: 12),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: DataTable(
                    columns: const [
                      DataColumn(label: Text('Estado item')),
                      DataColumn(label: Text('Item ID')),
                      DataColumn(label: Text('Titulo')),
                      DataColumn(label: Text('Seller ID')),
                      DataColumn(label: Text('Tienda oficial ID')),
                      DataColumn(label: Text('Seller')),
                      DataColumn(label: Text('Estado expansion seller')),
                      DataColumn(label: Text('Tipo')),
                      DataColumn(label: Text('Precio')),
                      DataColumn(label: Text('Superficie terreno')),
                      DataColumn(label: Text('Region')),
                      DataColumn(label: Text('Comuna')),
                      DataColumn(label: Text('Resultado')),
                    ],
                    rows: [
                      for (final item in items)
                        DataRow(
                          cells: [
                            DataCell(Text(_value(item['item_status']))),
                            DataCell(Text(_value(item['item_id']))),
                            DataCell(
                              SizedBox(
                                width: 260,
                                child: Text(
                                  _value(item['title']),
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ),
                            ),
                            DataCell(Text(_value(item['seller_id']))),
                            DataCell(Text(_value(item['official_store_id']))),
                            DataCell(Text(_value(item['seller_nickname']))),
                            DataCell(
                              Text(_value(item['seller_expansion_status'])),
                            ),
                            DataCell(Text(_value(item['type']))),
                            DataCell(Text(_value(item['price']))),
                            DataCell(Text(_value(item['surface']))),
                            DataCell(Text(_value(item['region']))),
                            DataCell(Text(_value(item['commune']))),
                            DataCell(Text(_value(item['result']))),
                          ],
                        ),
                    ],
                  ),
                ),
              ),
            ),
          ],
          if (_mercadoLibreImportSummary != null) ...[
            const SizedBox(height: 12),
            _MercadoLibreImportSummary(preview: _mercadoLibreImportSummary!),
          ],
          if (_mercadoLibreImportHistory.isNotEmpty) ...[
            const SizedBox(height: 12),
            Text(
              'Ultimas importaciones',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 8),
            for (final item in _mercadoLibreImportHistory.take(5))
              Text(
                '${_value(item['imported_at'])} | entradas ${_value(item['entries'])} | nuevos ${_value(item['new'])} | actualizados ${_value(item['updated'])} | descartados ${_value(item['discarded'])}',
              ),
          ],
        ],
      ),
    );
  }

  String _value(Object? value) {
    final text = value?.toString() ?? '';
    return text.isEmpty ? '-' : text;
  }

  Widget _buildExports() {
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const _PanelTitle(
                    icon: Icons.file_download_outlined,
                    title: 'Excel',
                  ),
                  const SizedBox(height: 12),
                  Text(
                    'Terrenos: ${_properties.length}',
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                  const SizedBox(height: 12),
                  FilledButton.icon(
                    onPressed: _exporting ? null : _exportExcel,
                    icon: _exporting
                        ? const SizedBox.square(
                            dimension: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.download_outlined),
                    label: Text(_exporting ? 'Exportando' : 'Crear workbook'),
                  ),
                  if (_exportPath != null) ...[
                    const SizedBox(height: 12),
                    SelectableText(
                      _exportPath!,
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSettings() {
    final mercadoPublicoConfigured = _isSecretConfigured(
      mercadoPublicoTicketKey,
      'has_mercado_publico_ticket',
    );
    final cmfConfigured = _isSecretConfigured(cmfApiKeyKey, 'has_cmf_api_key');
    final mercadoLibreConfigured = _isMercadoLibreConfigured;
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const _PanelTitle(
                    icon: Icons.vpn_key_outlined,
                    title: 'Fuentes y credenciales',
                  ),
                  const SizedBox(height: 12),
                  _CredentialSourceCard(
                    title: 'Mercado Publico',
                    subtitle:
                        'Ticket oficial de ChileCompra para consultar licitaciones reales.',
                    configured: mercadoPublicoConfigured,
                    child: Wrap(
                      spacing: 12,
                      runSpacing: 12,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: [
                        _InputBox(
                          controller: _mercadoPublicoTicketController,
                          label: 'Ticket Mercado Publico',
                          icon: Icons.key_outlined,
                          obscure: true,
                        ),
                        FilledButton.icon(
                          onPressed: _savingSettings
                              ? null
                              : () => _saveSourceSecret(
                                  mercadoPublicoTicketKey,
                                  _mercadoPublicoTicketController,
                                ),
                          icon: const Icon(Icons.save_outlined),
                          label: const Text('Configurar'),
                        ),
                        OutlinedButton.icon(
                          onPressed:
                              _testingCredentialSource == 'mercado_publico'
                              ? null
                              : () => _testCredential('mercado_publico'),
                          icon: _testingCredentialSource == 'mercado_publico'
                              ? const SizedBox.square(
                                  dimension: 18,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                  ),
                                )
                              : const Icon(Icons.network_check_outlined),
                          label: const Text('Probar conexion'),
                        ),
                        if (mercadoPublicoConfigured)
                          IconButton.filledTonal(
                            tooltip: 'Eliminar credencial',
                            onPressed: _savingSettings
                                ? null
                                : () => _deleteSourceSecret(
                                    mercadoPublicoTicketKey,
                                  ),
                            icon: const Icon(Icons.delete_outline),
                          ),
                      ],
                    ),
                    diagnostic: _credentialDiagnostics['mercado_publico'],
                  ),
                  const SizedBox(height: 14),
                  _CredentialSourceCard(
                    title: 'Mercado Libre / PortalInmobiliario',
                    subtitle:
                        'Conexion OAuth con Authorization Code; los tokens quedan en el backend local.',
                    configured: mercadoLibreConfigured,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Estado: PARTIAL'),
                        Text(
                          'OAuth: ${mercadoLibreConfigured ? 'CONNECTED' : 'NO CONFIGURADO'}',
                        ),
                        Text('Busqueda global: NO HABILITADA POR ML'),
                        Text(
                          'Sellers conectados: ${_settings['mercadolibre_partner_sellers_count'] ?? 0}',
                        ),
                        const SizedBox(height: 12),
                        Wrap(
                          spacing: 12,
                          runSpacing: 12,
                          children: [
                            _InputBox(
                              controller: _mercadoLibreClientIdController,
                              label: 'Client ID',
                              icon: Icons.badge_outlined,
                            ),
                            _InputBox(
                              controller: _mercadoLibreRedirectUriController,
                              label: 'Redirect URI',
                              icon: Icons.link_outlined,
                            ),
                            _InputBox(
                              controller: _mercadoLibreClientSecretController,
                              label: 'Client secret',
                              icon: Icons.key_outlined,
                              obscure: true,
                            ),
                            _InputBox(
                              controller: _mercadoLibrePartnerSellersController,
                              label: 'Seller IDs',
                              icon: Icons.storefront_outlined,
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        Wrap(
                          spacing: 10,
                          runSpacing: 10,
                          children: [
                            FilledButton.icon(
                              onPressed: _connectingMercadoLibre
                                  ? null
                                  : _connectMercadoLibre,
                              icon: _connectingMercadoLibre
                                  ? const SizedBox.square(
                                      dimension: 18,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                      ),
                                    )
                                  : const Icon(Icons.login_outlined),
                              label: Text(
                                _connectingMercadoLibre
                                    ? 'Conectando'
                                    : 'Conectar Mercado Libre',
                              ),
                            ),
                            OutlinedButton.icon(
                              onPressed: _savingSettings
                                  ? null
                                  : () => _saveSourceSecret(
                                      mercadoLibrePartnerSellerIdsKey,
                                      _mercadoLibrePartnerSellersController,
                                    ),
                              icon: const Icon(Icons.save_outlined),
                              label: const Text('Guardar sellers'),
                            ),
                            OutlinedButton.icon(
                              onPressed:
                                  _testingCredentialSource ==
                                      'mercadolibre_real_estate'
                                  ? null
                                  : () => _testCredential(
                                      'mercadolibre_real_estate',
                                    ),
                              icon:
                                  _testingCredentialSource ==
                                      'mercadolibre_real_estate'
                                  ? const SizedBox.square(
                                      dimension: 18,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                      ),
                                    )
                                  : const Icon(Icons.network_check_outlined),
                              label: const Text('Probar conexion'),
                            ),
                            if (mercadoLibreConfigured)
                              IconButton.filledTonal(
                                tooltip: 'Eliminar tokens',
                                onPressed: _savingSettings
                                    ? null
                                    : () async {
                                        await _deleteSourceSecret(
                                          mercadoLibreAccessTokenKey,
                                        );
                                        await _deleteSourceSecret(
                                          mercadoLibreRefreshTokenKey,
                                        );
                                        await _deleteSourceSecret(
                                          mercadoLibreAccessTokenExpiresAtKey,
                                        );
                                      },
                                icon: const Icon(Icons.delete_outline),
                              ),
                          ],
                        ),
                      ],
                    ),
                    diagnostic:
                        _credentialDiagnostics['mercadolibre_real_estate'],
                  ),
                  const SizedBox(height: 16),
                  _CredentialSourceCard(
                    title: 'CMF',
                    subtitle:
                        'Clave para consultar UF desde la API oficial cuando este disponible.',
                    configured: cmfConfigured,
                    child: Wrap(
                      spacing: 12,
                      runSpacing: 12,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: [
                        _InputBox(
                          controller: _cmfTokenController,
                          label: 'Clave CMF',
                          icon: Icons.key_outlined,
                          obscure: true,
                        ),
                        FilledButton.icon(
                          onPressed: _savingSettings
                              ? null
                              : () => _saveSourceSecret(
                                  cmfApiKeyKey,
                                  _cmfTokenController,
                                ),
                          icon: const Icon(Icons.save_outlined),
                          label: const Text('Configurar'),
                        ),
                        OutlinedButton.icon(
                          onPressed: _testingCredentialSource == 'cmf'
                              ? null
                              : () => _testCredential('cmf'),
                          icon: _testingCredentialSource == 'cmf'
                              ? const SizedBox.square(
                                  dimension: 18,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                  ),
                                )
                              : const Icon(Icons.network_check_outlined),
                          label: const Text('Probar conexion'),
                        ),
                        if (cmfConfigured)
                          IconButton.filledTonal(
                            tooltip: 'Eliminar credencial',
                            onPressed: _savingSettings
                                ? null
                                : () => _deleteSourceSecret(cmfApiKeyKey),
                            icon: const Icon(Icons.delete_outline),
                          ),
                      ],
                    ),
                    diagnostic: _credentialDiagnostics['cmf'],
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const _PanelTitle(
                    icon: Icons.terminal_outlined,
                    title: 'Backend',
                  ),
                  const SizedBox(height: 12),
                  for (final line in widget.api.logs().reversed.take(12))
                    SelectableText(
                      line,
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Map<String, dynamic>? _healthFor(String sourceId) {
    for (final item in _sourceHealth) {
      if (item['source_id'] == sourceId) {
        return item;
      }
    }
    return null;
  }
}

class _DisabledServiceRow extends StatelessWidget {
  const _DisabledServiceRow({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          const Checkbox(value: false, onChanged: null),
          const SizedBox(width: 6),
          const Icon(Icons.lock_clock_outlined, size: 20),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label),
                Text('Futuro', style: Theme.of(context).textTheme.bodySmall),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

double? _parseDouble(String value) {
  final clean = value.trim().replaceAll('.', '').replaceAll(',', '.');
  if (clean.isEmpty) {
    return null;
  }
  return double.tryParse(clean);
}

int? _parseInt(String value) {
  final clean = value.trim().replaceAll('.', '').replaceAll(',', '');
  if (clean.isEmpty) {
    return null;
  }
  return int.tryParse(clean);
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

Map<String, dynamic> _asMap(dynamic value) {
  if (value is Map) {
    return Map<String, dynamic>.from(value);
  }
  return {};
}

String _sourceTypeLabel(dynamic value) {
  return switch (value?.toString()) {
    'public_procurement' => 'Oportunidad publica',
    'marketplace' => 'Propiedad',
    _ => _knownText(value),
  };
}

String _confidenceText(dynamic value) {
  final confidence = _asDouble(value);
  if (confidence == null) {
    return 'Sin informacion';
  }
  final percent = confidence <= 1 ? confidence * 100 : confidence;
  return '${percent.round()}%';
}

String _yesNoText(dynamic value) {
  if (value == true || value == 1 || value?.toString() == '1') {
    return 'Si';
  }
  if (value == false || value == 0 || value?.toString() == '0') {
    return 'No';
  }
  return 'Sin informacion';
}

String _amountText(Map<String, dynamic> record) {
  final raw = record['amount_raw']?.toString().trim();
  if (raw != null && raw.isNotEmpty) {
    return raw;
  }
  final amount = _knownNumber(record['amount']);
  final currency = record['currency']?.toString();
  if (amount == 'Sin informacion') {
    return amount;
  }
  return currency == null || currency.isEmpty ? amount : '$currency $amount';
}

String? _sourceUrlFromRecord(Map<String, dynamic> record) {
  final value = record['source_url']?.toString().trim() ?? '';
  if (value.startsWith('https://') || value.startsWith('http://')) {
    return value;
  }
  return null;
}

bool _hasValidPropertyLocation(Map<String, dynamic> property) {
  final latitude = _asDouble(property['latitude']);
  final longitude = _asDouble(property['longitude']);
  if (latitude == null || longitude == null) {
    return false;
  }
  final precision = property['location_precision']?.toString() ?? 'UNKNOWN';
  return {
    'PARCEL_POLYGON',
    'EXACT_COORDINATES',
    'VERIFIED_ADDRESS',
    'STREET_ADDRESS',
    'EXACT',
    'APPROXIMATE_PROPERTY',
  }.contains(precision);
}

Map<String, dynamic>? _latestEvidence(
  List<Map<String, dynamic>> evidence,
  String field,
) {
  for (final item in evidence) {
    if (item['field']?.toString() == field) {
      return item;
    }
  }
  return null;
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

String _joinList(dynamic value) {
  final decoded = _decodeMaybeJson(value);
  if (decoded is List) {
    return decoded.map((item) => item.toString()).join(', ');
  }
  return decoded?.toString() ?? '';
}

String _urbanLimitLabel(dynamic value) {
  final text = _decodeMaybeJson(value)?.toString() ?? '';
  return switch (text) {
    'YES' => 'Si',
    'NO' => 'No',
    'UNKNOWN' => 'Desconocido',
    '' => 'No verificado',
    _ => text,
  };
}

String _riskStatusLabel(dynamic value) {
  final text = _decodeMaybeJson(value)?.toString() ?? '';
  return switch (text) {
    'INTERSECTION_DETECTED' => 'Interseccion detectada',
    'NO_INTERSECTION_DETECTED' => 'Sin interseccion detectada',
    'SOURCE_UNAVAILABLE' => 'Fuente no disponible',
    'LAYER_NOT_APPLICABLE' => 'Capa no aplicable',
    'UNKNOWN' => 'Desconocido',
    '' => 'No verificado',
    _ => text,
  };
}

String _adminStatusLabel(String value) {
  return switch (value) {
    'MATCH' => 'Coincide',
    'COMMUNE_MISMATCH' => 'Comuna no coincide',
    'REGION_MISMATCH' => 'Region no coincide',
    'COMMUNE_AND_REGION_MISMATCH' => 'Comuna y region no coinciden',
    'OUTSIDE_CHILE' => 'Fuera de Chile',
    'GEOMETRY_INVALID' => 'Geometria invalida',
    'GEOMETRY_UNKNOWN' => 'Geometria no verificada',
    'SOURCE_ADMIN_UNKNOWN' => 'Fuente sin comuna/region',
    _ => value,
  };
}

String _dimensionsText(Map<String, dynamic> metrics) {
  final width = _asDouble(metrics['estimated_width_m']);
  final depth = _asDouble(metrics['estimated_depth_m']);
  if (width == null || depth == null) {
    return 'No verificado';
  }
  return '${width.toStringAsFixed(1)} m x ${depth.toStringAsFixed(1)} m';
}

String _shapeText(Map<String, dynamic> metrics) {
  final compactness = _asDouble(metrics['compactness_index']);
  final elongation = _asDouble(metrics['elongation']);
  if (compactness == null && elongation == null) {
    return 'No verificado';
  }
  final parts = <String>[];
  if (compactness != null) {
    parts.add('compactacion ${compactness.toStringAsFixed(2)}');
  }
  if (elongation != null) {
    parts.add('elongacion ${elongation.toStringAsFixed(2)}');
  }
  return parts.join(' | ');
}

String _evidenceValueText(dynamic value) {
  final decoded = _decodeMaybeJson(value);
  if (decoded is Map || decoded is List) {
    return jsonEncode(decoded);
  }
  return _knownText(decoded);
}

String _evidenceDateText(dynamic value) {
  return _knownText(value);
}

String _evidenceConfidenceText(dynamic value) {
  final confidence = _asDouble(value);
  if (confidence == null) {
    return 'Sin confianza';
  }
  final percent = confidence <= 1 ? confidence * 100 : confidence;
  return '${percent.round()}%';
}

String _provenanceLabel(String field) {
  return switch (field) {
    'asking_price_clp' => 'Precio CLP',
    'asking_price_uf' => 'Precio UF',
    'uf_rate' => 'UF',
    'price_uf_m2_gross' => 'UF/m2',
    'inside_urban_limit' => 'Limite urbano',
    'prc_applicable' => 'PRC',
    'urban_zone' => 'Zona',
    'risk_intersection' => 'Riesgo',
    _ => field,
  };
}

String? _sourceUrl(Map<String, dynamic> evidence) {
  final raw = evidence['source_url'] ?? evidence['url'];
  final url = raw?.toString().trim() ?? '';
  if (url.startsWith('https://') || url.startsWith('http://')) {
    return url;
  }
  return null;
}

class _MercadoLibreImportSummary extends StatelessWidget {
  const _MercadoLibreImportSummary({required this.preview});

  final Map<String, dynamic> preview;

  @override
  Widget build(BuildContext context) {
    final chips = [
      ('Entradas pegadas', preview['entries']),
      ('IDs detectados', preview['ids_detected']),
      ('Duplicados', preview['duplicates']),
      ('Nuevos sellers', preview['new_sellers']),
      if (preview.containsKey('new')) ('Nuevos', preview['new']),
      if (preview.containsKey('updated')) ('Actualizados', preview['updated']),
      if (preview.containsKey('discarded'))
        ('Descartados', preview['discarded']),
    ];
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        for (final item in chips)
          Chip(label: Text('${item.$1}: ${item.$2 ?? 0}')),
      ],
    );
  }
}

String _credentialStatusLabel(String status) {
  return switch (status) {
    'CONNECTED' => 'Configurado',
    'INVALID_CREDENTIAL' => 'Credencial invalida',
    'EXPIRED' => 'Requiere reconexion',
    'RATE_LIMITED' => 'Limite de tasa',
    'UNAVAILABLE' => 'No disponible',
    'NOT_CONFIGURED' => 'No configurado',
    _ => status,
  };
}

IconData _credentialStatusIcon(String status) {
  return switch (status) {
    'CONNECTED' => Icons.check_circle_outline,
    'INVALID_CREDENTIAL' => Icons.error_outline,
    'EXPIRED' => Icons.sync_problem_outlined,
    'RATE_LIMITED' => Icons.speed_outlined,
    'UNAVAILABLE' => Icons.cloud_off_outlined,
    'NOT_CONFIGURED' => Icons.radio_button_unchecked,
    _ => Icons.help_outline,
  };
}

Color _credentialStatusColor(String status) {
  return switch (status) {
    'CONNECTED' => const Color(0xFF047857),
    'INVALID_CREDENTIAL' => const Color(0xFFB91C1C),
    'EXPIRED' => const Color(0xFFB45309),
    'RATE_LIMITED' => const Color(0xFF7C3AED),
    'UNAVAILABLE' => const Color(0xFF475569),
    'NOT_CONFIGURED' => const Color(0xFF64748B),
    _ => const Color(0xFF64748B),
  };
}

String _joinMessages(dynamic value) {
  if (value is List) {
    return value.map((item) => item.toString()).join(' | ');
  }
  return value?.toString() ?? '';
}

IconData _eventIcon(String type) {
  return switch (type) {
    'warning' => Icons.warning_amber_outlined,
    'error' => Icons.error_outline,
    'completed' => Icons.check_circle_outline,
    'started' => Icons.play_circle_outline,
    _ => Icons.radio_button_checked,
  };
}

Color _eventColor(String type) {
  return switch (type) {
    'warning' => const Color(0xFFB45309),
    'error' => const Color(0xFFB91C1C),
    'completed' => const Color(0xFF047857),
    'started' => const Color(0xFF2563EB),
    _ => const Color(0xFF64748B),
  };
}

Color _softColor(Color color) {
  if (color == const Color(0xFF047857)) {
    return const Color(0xFFECFDF5);
  }
  if (color == const Color(0xFFB45309)) {
    return const Color(0xFFFFFBEB);
  }
  if (color == const Color(0xFFB91C1C)) {
    return const Color(0xFFFEF2F2);
  }
  return const Color(0xFFF1F5F9);
}
