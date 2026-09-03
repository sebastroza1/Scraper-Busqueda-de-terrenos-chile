import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
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
      TextEditingController(
        text: 'http://127.0.0.1:8766/oauth/mercadolibre/callback',
      );

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
  Map<String, dynamic>? _customKeywordPreset;
  Map<String, dynamic> _settings = {};
  Map<String, dynamic>? _job;
  Map<String, dynamic>? _audit;
  Map<String, dynamic>? _selectedProperty;
  Map<String, dynamic>? _selectedSourceRecord;
  Map<String, bool> _secretStatus = {};
  final Map<String, Map<String, dynamic>> _credentialDiagnostics = {};
  final Map<String, Map<String, dynamic>> _territoryByProperty = {};
  Set<String> _selectedSources = {};
  Set<String> _selectedEnrichmentSources = {'cmf_uf', 'minvu'};
  Set<String> _selectedCommunes = {};
  final Map<String, bool> _keywordEnabled = {};
  String? _selectedRegionCode = 'ALL';
  String _keywordMode = 'ANY';
  String? _latestSearchId;
  String _sourceRecordBucket = 'candidates';
  Timer? _jobTimer;
  bool _booting = true;
  bool _searching = false;
  bool _savingSettings = false;
  String? _testingCredentialSource;
  bool _connectingMercadoLibre = false;
  bool _refreshingTerritory = false;
  bool _showLandLayer = true;
  bool _showUrbanLimitLayer = true;
  bool _showRiskLayer = true;
  bool _showZoningLayer = true;
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
      _properties = List<Map<String, dynamic>>.from(
        propertiesPayload['items'] as List? ?? const [],
      );
      _secretStatus = Map<String, bool>.from(results[8] as Map);
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
      _selectedCommunes = _selectedCommunes
          .where(
            (commune) =>
                _communesCatalog.any((item) => item['name'] == commune),
          )
          .toSet();
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
      'communes': _selectedCommunes.toList()..sort(),
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
      _selectedCommunes = _selectedCommunes
          .where((commune) => communes.any((item) => item['name'] == commune))
          .toSet();
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
      setState(() => _sourceRecords = records);
    }
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
      final result = await widget.api.connectMercadoLibre(
        clientId: _mercadoLibreClientIdController.text,
        clientSecret: _mercadoLibreClientSecretController.text,
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
      final territory = await widget.api.refreshPropertyTerritory(
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
          ),
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
          const SizedBox(height: 16),
          FilledButton.icon(
            onPressed: _searching ? null : _startSearch,
            icon: _searching
                ? const SizedBox.square(
                    dimension: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.play_arrow_outlined),
            label: Text(_searching ? 'Buscando' : 'Iniciar busqueda'),
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
            _selectedCommunes.clear();
          });
          unawaited(_loadCommunes(value));
        },
      ),
    );
  }

  Widget _buildCommuneSelector() {
    final allActive = _selectedCommunes.isEmpty;
    final catalogUnavailable = _communesCatalog.isEmpty;
    final addLabel = catalogUnavailable ? 'Cargar comunas' : 'Agregar comuna';
    return SizedBox(
      width: 360,
      child: InputDecorator(
        decoration: const InputDecoration(
          border: OutlineInputBorder(
            borderRadius: BorderRadius.all(Radius.circular(8)),
          ),
          prefixIcon: Icon(Icons.location_city_outlined),
          labelText: 'Comunas',
          isDense: true,
        ),
        child: Wrap(
          spacing: 6,
          runSpacing: 6,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            if (allActive)
              const Chip(label: Text('Todas las comunas'))
            else
              for (final commune in _selectedCommunes.toList()..sort())
                InputChip(
                  label: Text(commune),
                  onDeleted: () {
                    setState(() => _selectedCommunes.remove(commune));
                  },
                ),
            ActionChip(
              avatar: const Icon(Icons.add_outlined, size: 18),
              label: Text(addLabel),
              onPressed: () => unawaited(_showCommunePicker()),
            ),
          ],
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
    final selected = Set<String>.from(_selectedCommunes);
    String query = '';
    String normalize(String value) => value
        .toLowerCase()
        .replaceAll(RegExp('[áàäâ]'), 'a')
        .replaceAll(RegExp('[éèëê]'), 'e')
        .replaceAll(RegExp('[íìïî]'), 'i')
        .replaceAll(RegExp('[óòöô]'), 'o')
        .replaceAll(RegExp('[úùüû]'), 'u')
        .replaceAll('ñ', 'n');
    final result = await showDialog<Set<String>>(
      context: context,
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
            return AlertDialog(
              title: const Text('Seleccionar comunas'),
              content: SizedBox(
                width: 620,
                height: 560,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    TextField(
                      decoration: const InputDecoration(
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.all(Radius.circular(8)),
                        ),
                        prefixIcon: Icon(Icons.search_outlined),
                        hintText: 'Buscar comuna o region',
                        isDense: true,
                      ),
                      onChanged: (value) {
                        setDialogState(() => query = value);
                      },
                    ),
                    const SizedBox(height: 12),
                    CheckboxListTile(
                      dense: true,
                      contentPadding: EdgeInsets.zero,
                      value: selected.isEmpty,
                      onChanged: (_) {
                        setDialogState(selected.clear);
                      },
                      title: const Text('Todas las comunas'),
                      subtitle: Text(
                        selected.isEmpty
                            ? 'Sin filtro comunal'
                            : '${selected.length} seleccionadas',
                      ),
                    ),
                    const Divider(height: 12),
                    Expanded(
                      child: filtered.isEmpty
                          ? const Center(
                              child: Text('No hay comunas para mostrar.'),
                            )
                          : ListView.builder(
                              itemCount: filtered.length,
                              itemBuilder: (context, index) {
                                final commune = filtered[index];
                                final name = commune['name']?.toString() ?? '';
                                final regionName = commune['region_name']
                                    ?.toString();
                                return CheckboxListTile(
                                  dense: true,
                                  value: selected.contains(name),
                                  onChanged: (value) {
                                    setDialogState(() {
                                      if (value == true) {
                                        selected.add(name);
                                      } else {
                                        selected.remove(name);
                                      }
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
                  ],
                ),
              ),
              actions: [
                TextButton(
                  onPressed: () {
                    setDialogState(selected.clear);
                  },
                  child: const Text('Limpiar'),
                ),
                TextButton(
                  onPressed: () => Navigator.of(context).pop(),
                  child: const Text('Cancelar'),
                ),
                FilledButton(
                  onPressed: () => Navigator.of(context).pop(selected),
                  child: const Text('Aplicar'),
                ),
              ],
            );
          },
        );
      },
    );
    if (result != null && mounted) {
      setState(() => _selectedCommunes = result);
    }
  }

  Widget _buildKeywordSelector() {
    final presets = [
      ..._keywordPresets,
      if (_customKeywordPreset != null) _customKeywordPreset!,
    ];
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
                    title: 'Palabras clave',
                  ),
                ),
                SegmentedButton<String>(
                  segments: const [
                    ButtonSegment(value: 'ANY', label: Text('ANY')),
                    ButtonSegment(value: 'ALL', label: Text('ALL')),
                  ],
                  selected: {_keywordMode},
                  onSelectionChanged: (value) {
                    setState(() => _keywordMode = value.first);
                  },
                ),
              ],
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final preset in presets)
                  ActionChip(
                    avatar: const Icon(Icons.bookmarks_outlined, size: 18),
                    label: Text(preset['name']?.toString() ?? ''),
                    onPressed: () {
                      setState(() => _applyPreset(preset, replace: false));
                    },
                  ),
                OutlinedButton.icon(
                  onPressed: () {
                    final recommended = _keywordPresets.firstWhere(
                      (item) => item['id'] == 'BUSQUEDA_TERRENOS_CHILE',
                      orElse: () => _keywordPresets.isEmpty
                          ? <String, dynamic>{}
                          : _keywordPresets.first,
                    );
                    setState(() => _applyPreset(recommended, replace: true));
                  },
                  icon: const Icon(Icons.restore_outlined),
                  label: const Text('Restaurar recomendadas'),
                ),
                OutlinedButton.icon(
                  onPressed: _activeKeywords().isEmpty
                      ? null
                      : () {
                          setState(() {
                            _customKeywordPreset = {
                              'id': 'CUSTOM_LOCAL',
                              'name': 'Personalizado',
                              'keywords': _activeKeywords(),
                              'default_mode': _keywordMode,
                            };
                          });
                        },
                  icon: const Icon(Icons.save_outlined),
                  label: const Text('Guardar preset'),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final entry in _keywordEnabled.entries)
                  InputChip(
                    selected: entry.value,
                    label: Text(entry.key),
                    onSelected: (value) {
                      setState(() => _keywordEnabled[entry.key] = value);
                    },
                    onDeleted: () {
                      setState(() => _keywordEnabled.remove(entry.key));
                    },
                  ),
              ],
            ),
            const SizedBox(height: 12),
            SizedBox(
              width: 360,
              child: TextField(
                controller: _keywordAddController,
                decoration: InputDecoration(
                  border: const OutlineInputBorder(
                    borderRadius: BorderRadius.all(Radius.circular(8)),
                  ),
                  prefixIcon: const Icon(Icons.add_outlined),
                  labelText: 'Agregar palabra',
                  suffixIcon: IconButton(
                    tooltip: 'Agregar',
                    onPressed: _addKeyword,
                    icon: const Icon(Icons.check_outlined),
                  ),
                ),
                onSubmitted: (_) => _addKeyword(),
              ),
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
        DataCell(Text(_knownText(record['automatic_classification']))),
        DataCell(Text(_confidenceText(record['automatic_confidence']))),
        DataCell(
          Text(_knownText(record['property_region'] ?? record['region'])),
        ),
        DataCell(
          Text(_knownText(record['property_commune'] ?? record['commune'])),
        ),
        DataCell(Text(_knownNumber(record['surface_m2'], suffix: ' m2'))),
        DataCell(Text(_amountText(record))),
        DataCell(Text(_knownNumber(property?['asking_price_uf']))),
        DataCell(Text(_knownText(record['publication_date']))),
        DataCell(
          SizedBox(
            width: 220,
            child: Text(
              _knownText(record['organization']),
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
    return _buildPropertyDetail();
  }

  Widget _buildPropertyDetail() {
    final property =
        _selectedProperty ??
        (_properties.isNotEmpty ? _properties.first : null);
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
              child: OutlinedButton.icon(
                onPressed: () => _showFullPropertyDetail(property),
                icon: const Icon(Icons.open_in_full_outlined),
                label: const Text('Ver detalle completo'),
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
                  tooltip: 'Actualizar informacion territorial',
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
              const _EmptyLine(
                text: 'Analisis MINVU pendiente: falta ubicacion del predio.',
              )
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
    final evidence = List<Map<String, dynamic>>.from(
      (territory?['evidence'] as List? ?? const []).whereType<Map>().map(
        (item) => Map<String, dynamic>.from(item),
      ),
    );
    final territoryProperty = _asMap(territory?['property']);
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
    Map<String, dynamic>? selected = _selectedProperty;
    if (selected == null) {
      for (final property in _properties) {
        if (_hasValidPropertyLocation(property)) {
          selected = property;
          break;
        }
      }
    }
    return LandfinderMapScreen(
      properties: _properties,
      selectedProperty: selected,
      territoryByProperty: _territoryByProperty,
      showLandLayer: _showLandLayer,
      showUrbanLimitLayer: _showUrbanLimitLayer,
      showRiskLayer: _showRiskLayer,
      showZoningLayer: _showZoningLayer,
      refreshingTerritory: _refreshingTerritory,
      onLandLayerChanged: (value) => setState(() => _showLandLayer = value),
      onUrbanLimitLayerChanged: (value) =>
          setState(() => _showUrbanLimitLayer = value),
      onRiskLayerChanged: (value) => setState(() => _showRiskLayer = value),
      onZoningLayerChanged: (value) => setState(() => _showZoningLayer = value),
      onSelectProperty: _selectProperty,
      onRefreshTerritory: () => _refreshSelectedTerritory(forceRefresh: false),
    );
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
                    title: 'Mercado Libre',
                    subtitle:
                        'Conexion OAuth con Authorization Code y PKCE; los tokens quedan en almacenamiento seguro.',
                    configured: mercadoLibreConfigured,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
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
                                    : 'Conectar',
                              ),
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
    'EXACT',
    'APPROXIMATE',
    'CENTROID',
    'APPROXIMATE_PROPERTY',
    'PROPERTY_COMMUNE_CENTROID',
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
