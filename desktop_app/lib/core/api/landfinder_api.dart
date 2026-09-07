import 'dart:async';
import 'dart:convert';
import 'dart:io';

import '../security/mercadolibre_oauth.dart';
import '../security/secret_store.dart';

abstract class LandfinderApi {
  Future<void> start();
  Future<Map<String, dynamic>> health();
  Future<List<Map<String, dynamic>>> sources();
  Future<List<Map<String, dynamic>>> enrichmentSources();
  Future<List<Map<String, dynamic>>> sourcesHealth();
  Future<Map<String, dynamic>> sourceAudit(String sourceId);
  Future<Map<String, dynamic>> regions();
  Future<Map<String, dynamic>> communes(String regionCode);
  Future<Map<String, dynamic>> keywordPresets();
  Future<Map<String, dynamic>> settings();
  Future<Map<String, dynamic>> mapProviders();
  Future<Map<String, dynamic>> updateSettings(Map<String, dynamic> values);
  Future<Map<String, dynamic>> createManualProperty(
    Map<String, dynamic> values,
  );
  Future<Map<String, dynamic>> geocode(Map<String, dynamic> values);
  Future<Map<String, dynamic>> assignPropertyLocation(
    String propertyId,
    Map<String, dynamic> values,
  );
  Future<Map<String, dynamic>> resolvePropertyLocation(String propertyId);
  Future<Map<String, dynamic>> propertyDiagnostics(String propertyId);
  Future<Map<String, dynamic>> startSearch(Map<String, dynamic> filters);
  Future<Map<String, dynamic>> search(String searchId);
  Future<Map<String, dynamic>> searchSourceRecords(
    String searchId, {
    String? bucket,
    String? q,
    int limit = 500,
  });
  Future<Map<String, dynamic>> updateManualClassification(
    String sourceRecordId,
    String manualClassification,
  );
  Future<Map<String, dynamic>> properties();
  Future<Map<String, dynamic>> propertyTerritory(String propertyId);
  Future<Map<String, dynamic>> refreshPropertyTerritory(
    String propertyId, {
    bool forceRefresh = false,
  });
  Future<Map<String, dynamic>> minvuServices();
  Future<Map<String, dynamic>> minvuIptCatalog({String? region});
  Future<Map<String, dynamic>> minvuLayerAudit({
    String? region,
    bool includeFeatureCounts = false,
  });
  Future<Map<String, dynamic>> minvuLayers({bool refresh = false});
  Future<Map<String, dynamic>> exportExcel();
  Future<Map<String, bool>> secretStatus();
  Future<void> saveSecret(String key, String value);
  Future<void> deleteSecret(String key);
  Future<Map<String, dynamic>> testCredential(String sourceId);
  Future<Map<String, dynamic>> connectMercadoLibre({
    required String clientId,
    required String redirectUri,
    String? clientSecret,
  });
  Future<bool> refreshMercadoLibreIfNeeded();
  List<String> logs();
  void dispose();
}

class ApiException implements Exception {
  ApiException(this.statusCode, this.message);

  final int statusCode;
  final String message;

  @override
  String toString() => 'HTTP $statusCode: $message';
}

class LocalLandfinderApi implements LandfinderApi {
  LocalLandfinderApi({this.port = 8765, SecretStore? secretStore})
    : _secretStore = secretStore ?? SecretStore.create();

  final int port;
  final SecretStore _secretStore;
  final HttpClient _client = HttpClient();
  final List<String> _logs = [];
  late final MercadoLibreOAuthFlow _mercadoLibreOAuth = MercadoLibreOAuthFlow(
    _secretStore,
  );
  Process? _process;
  String? _token;
  int? _runtimePort;

  Uri get _base =>
      Uri(scheme: 'http', host: '127.0.0.1', port: _runtimePort ?? port);

  @override
  Future<void> start() async {
    _runtimePort = port;
    if (await _isAlive()) {
      await _loadSessionToken();
      if (await _isCompatibleBackend()) {
        return;
      }
      _appendLog(
        'running backend is missing catalog endpoints; starting another local backend',
      );
      _runtimePort = await _findAvailablePort(port + 1);
    }
    await _startBackendProcess();
    await _waitForBackend();
    await _loadSessionToken();
  }

  @override
  Future<Map<String, dynamic>> health() async {
    return _map(await _request('GET', '/health', authenticated: false));
  }

  @override
  Future<List<Map<String, dynamic>>> sources() async {
    return _list(await _request('GET', '/sources'));
  }

  @override
  Future<List<Map<String, dynamic>>> enrichmentSources() async {
    return _list(await _request('GET', '/enrichment-sources'));
  }

  @override
  Future<List<Map<String, dynamic>>> sourcesHealth() async {
    return _list(await _request('GET', '/sources/health'));
  }

  @override
  Future<Map<String, dynamic>> sourceAudit(String sourceId) async {
    return _map(await _request('GET', '/sources/$sourceId/audit'));
  }

  @override
  Future<Map<String, dynamic>> regions() async {
    try {
      return _map(await _request('GET', '/catalog/regions'));
    } on ApiException catch (error) {
      if (error.statusCode == 404) {
        _appendLog('catalog regions unavailable on running backend');
        return {'items': <Map<String, dynamic>>[]};
      }
      rethrow;
    }
  }

  @override
  Future<Map<String, dynamic>> communes(String regionCode) async {
    try {
      return _map(
        await _request('GET', '/catalog/regions/$regionCode/communes'),
      );
    } on ApiException catch (error) {
      if (error.statusCode == 404) {
        _appendLog('catalog communes unavailable for $regionCode');
        return {'region_code': regionCode, 'items': <Map<String, dynamic>>[]};
      }
      rethrow;
    }
  }

  @override
  Future<Map<String, dynamic>> keywordPresets() async {
    try {
      return _map(await _request('GET', '/catalog/search-keyword-presets'));
    } on ApiException catch (error) {
      if (error.statusCode == 404) {
        _appendLog('keyword presets unavailable on running backend');
        return {'items': <Map<String, dynamic>>[]};
      }
      rethrow;
    }
  }

  @override
  Future<Map<String, dynamic>> settings() async {
    return _map(await _request('GET', '/settings'));
  }

  @override
  Future<Map<String, dynamic>> mapProviders() async {
    return _map(await _request('GET', '/map/providers'));
  }

  @override
  Future<Map<String, dynamic>> updateSettings(
    Map<String, dynamic> values,
  ) async {
    final filtered = <String, dynamic>{};
    for (final entry in values.entries) {
      if (entry.value is String && (entry.value as String).trim().isEmpty) {
        continue;
      }
      if (entry.value != null) {
        filtered[entry.key] = entry.value;
      }
    }
    return _map(await _request('PUT', '/settings', body: filtered));
  }

  @override
  Future<Map<String, dynamic>> createManualProperty(
    Map<String, dynamic> values,
  ) async {
    return _map(await _request('POST', '/properties', body: values));
  }

  @override
  Future<Map<String, dynamic>> geocode(Map<String, dynamic> values) async {
    return _map(await _request('POST', '/geocode', body: values));
  }

  @override
  Future<Map<String, dynamic>> assignPropertyLocation(
    String propertyId,
    Map<String, dynamic> values,
  ) async {
    return _map(
      await _request('PUT', '/properties/$propertyId/location', body: values),
    );
  }

  @override
  Future<Map<String, dynamic>> resolvePropertyLocation(
    String propertyId,
  ) async {
    return _map(
      await _request('POST', '/properties/$propertyId/location/resolve'),
    );
  }

  @override
  Future<Map<String, dynamic>> propertyDiagnostics(String propertyId) async {
    return _map(await _request('GET', '/properties/$propertyId/diagnostics'));
  }

  @override
  Future<Map<String, dynamic>> startSearch(Map<String, dynamic> filters) async {
    await refreshMercadoLibreIfNeeded();
    await _pushSecretsToRunningBackend();
    return _map(await _request('POST', '/searches', body: filters));
  }

  @override
  Future<Map<String, dynamic>> search(String searchId) async {
    return _map(await _request('GET', '/searches/$searchId'));
  }

  @override
  Future<Map<String, dynamic>> searchSourceRecords(
    String searchId, {
    String? bucket,
    String? q,
    int limit = 500,
  }) async {
    try {
      return _map(
        await _request(
          'GET',
          '/searches/$searchId/source-records',
          query: {
            'limit': '$limit',
            if (bucket != null && bucket != 'all') 'bucket': bucket,
            if (q != null && q.trim().isNotEmpty) 'q': q.trim(),
          },
        ),
      );
    } on ApiException catch (error) {
      if (error.statusCode == 404) {
        _appendLog('source records unavailable for search $searchId');
        return {
          'items': <Map<String, dynamic>>[],
          'total': 0,
          'limit': limit,
          'offset': 0,
          'classifier_distribution': <String, dynamic>{},
        };
      }
      rethrow;
    }
  }

  @override
  Future<Map<String, dynamic>> updateManualClassification(
    String sourceRecordId,
    String manualClassification,
  ) async {
    return _map(
      await _request(
        'PUT',
        '/source-records/$sourceRecordId/manual-classification',
        body: {'manual_classification': manualClassification},
      ),
    );
  }

  @override
  Future<Map<String, dynamic>> properties() async {
    return _map(await _request('GET', '/properties', query: {'limit': '500'}));
  }

  @override
  Future<Map<String, dynamic>> propertyTerritory(String propertyId) async {
    return _map(await _request('GET', '/properties/$propertyId/territory'));
  }

  @override
  Future<Map<String, dynamic>> refreshPropertyTerritory(
    String propertyId, {
    bool forceRefresh = false,
  }) async {
    return _map(
      await _request(
        'POST',
        '/properties/$propertyId/territory/refresh',
        query: {'force_refresh': forceRefresh ? 'true' : 'false'},
      ),
    );
  }

  @override
  Future<Map<String, dynamic>> minvuServices() async {
    return _map(await _request('GET', '/gis/minvu/services'));
  }

  @override
  Future<Map<String, dynamic>> minvuIptCatalog({String? region}) async {
    return _map(
      await _request(
        'GET',
        '/gis/minvu/ipt/catalog',
        query: {
          if (region != null && region.trim().isNotEmpty) 'region': region,
        },
      ),
    );
  }

  @override
  Future<Map<String, dynamic>> minvuLayerAudit({
    String? region,
    bool includeFeatureCounts = false,
  }) async {
    return _map(
      await _request(
        'GET',
        '/gis/minvu/layer-audit',
        query: {
          if (region != null && region.trim().isNotEmpty) 'region': region,
          if (includeFeatureCounts) 'include_feature_counts': 'true',
        },
      ),
    );
  }

  @override
  Future<Map<String, dynamic>> minvuLayers({bool refresh = false}) async {
    return _map(
      await _request(
        'GET',
        '/gis/minvu/layers',
        query: {if (refresh) 'refresh': 'true'},
      ),
    );
  }

  @override
  Future<Map<String, dynamic>> exportExcel() async {
    return _map(await _request('POST', '/exports/excel'));
  }

  @override
  Future<Map<String, bool>> secretStatus() {
    return _secretStore.status(supportedSecretKeys);
  }

  @override
  Future<void> saveSecret(String key, String value) async {
    final trimmed = value.trim();
    if (trimmed.isEmpty) {
      return;
    }
    await _secretStore.write(key, trimmed);
    await _pushSecretsToRunningBackend();
  }

  @override
  Future<void> deleteSecret(String key) async {
    await _secretStore.delete(key);
    await _pushSecretsToRunningBackend();
  }

  @override
  Future<Map<String, dynamic>> testCredential(String sourceId) async {
    await refreshMercadoLibreIfNeeded();
    await _pushSecretsToRunningBackend();
    return _map(await _request('POST', '/credentials/diagnostics/$sourceId'));
  }

  @override
  Future<Map<String, dynamic>> connectMercadoLibre({
    required String clientId,
    required String redirectUri,
    String? clientSecret,
  }) async {
    await _secretStore.write(mercadoLibreClientIdKey, clientId.trim());
    await _secretStore.write(mercadoLibreRedirectUriKey, redirectUri.trim());
    if (clientSecret != null && clientSecret.trim().isNotEmpty) {
      await _secretStore.write(
        mercadoLibreClientSecretKey,
        clientSecret.trim(),
      );
    }
    final result = await _mercadoLibreOAuth.authorize(
      clientId: clientId.trim(),
      clientSecret: clientSecret?.trim(),
      redirectUri: redirectUri.trim(),
    );
    await _pushSecretsToRunningBackend();
    return result.toJson();
  }

  @override
  Future<bool> refreshMercadoLibreIfNeeded() async {
    final expiresRaw = await _secretStore.read(
      mercadoLibreAccessTokenExpiresAtKey,
    );
    final refreshToken = await _secretStore.read(mercadoLibreRefreshTokenKey);
    final clientId = await _secretStore.read(mercadoLibreClientIdKey);
    if (expiresRaw == null || refreshToken == null || clientId == null) {
      return false;
    }
    final expiresAt = DateTime.tryParse(expiresRaw);
    if (expiresAt == null ||
        expiresAt.toUtc().isAfter(
          DateTime.now().toUtc().add(const Duration(minutes: 10)),
        )) {
      return false;
    }
    final clientSecret = await _secretStore.read(mercadoLibreClientSecretKey);
    await _mercadoLibreOAuth.refresh(
      clientId: clientId,
      clientSecret: clientSecret,
      refreshToken: refreshToken,
    );
    await _pushSecretsToRunningBackend();
    return true;
  }

  @override
  List<String> logs() => List.unmodifiable(_logs);

  @override
  void dispose() {
    _client.close(force: true);
    final process = _process;
    if (process != null) {
      process.kill();
      _process = null;
    }
  }

  Future<void> _startBackendProcess() async {
    final repoRoot = _findRepoRoot();
    final pythonEngine = Directory(_join(repoRoot.path, 'python_engine'));
    final venvPython = File(
      _join(
        pythonEngine.path,
        '.venv',
        Platform.isWindows ? 'Scripts' : 'bin',
        Platform.isWindows ? 'python.exe' : 'python',
      ),
    );
    final pythonPath = venvPython.existsSync() ? venvPython.path : 'python';
    final dataDir = _join(repoRoot.path, 'data');
    final backendSecrets = await _backendSecretEnvironment();
    final activePort = _runtimePort ?? port;
    _appendLog('starting backend on port $activePort: $pythonPath');
    _process = await Process.start(
      pythonPath,
      ['-m', 'landfinder', '--port', '$activePort', '--data-dir', dataDir],
      workingDirectory: pythonEngine.path,
      environment: {'PYTHONUTF8': '1', ...backendSecrets},
      includeParentEnvironment: true,
    );
    _process!.stdout
        .transform(utf8.decoder)
        .transform(const LineSplitter())
        .listen((line) {
          _appendLog(line);
          const prefix = 'LANDFINDER_SESSION_TOKEN=';
          if (line.startsWith(prefix)) {
            _token = line.substring(prefix.length).trim();
          }
        });
    _process!.stderr
        .transform(utf8.decoder)
        .transform(const LineSplitter())
        .listen(_appendLog);
  }

  Directory _findRepoRoot() {
    final candidates = <Directory>[
      Directory.current.absolute,
      Directory.current.absolute.parent,
      File(Platform.resolvedExecutable).parent,
      File(Platform.resolvedExecutable).parent.parent,
    ];
    for (final candidate in candidates) {
      if (Directory(_join(candidate.path, 'python_engine')).existsSync()) {
        return candidate;
      }
    }
    return Directory.current.absolute.parent;
  }

  Future<bool> _isAlive() async {
    try {
      await health().timeout(const Duration(seconds: 2));
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<bool> _isCompatibleBackend() async {
    try {
      final payload = _map(await _request('GET', '/catalog/regions'));
      final items = payload['items'];
      return items is List && items.isNotEmpty;
    } catch (_) {
      return false;
    }
  }

  Future<int> _findAvailablePort(int firstPort) async {
    for (
      var candidate = firstPort;
      candidate < firstPort + 20;
      candidate += 1
    ) {
      ServerSocket? socket;
      try {
        socket = await ServerSocket.bind(
          InternetAddress.loopbackIPv4,
          candidate,
        );
        return candidate;
      } on SocketException {
        continue;
      } finally {
        await socket?.close();
      }
    }
    throw StateError('No hay puerto local disponible para iniciar Landfinder.');
  }

  Future<void> _waitForBackend() async {
    for (var index = 0; index < 60; index += 1) {
      if (await _isAlive()) {
        return;
      }
      await Future<void>.delayed(const Duration(milliseconds: 250));
    }
    throw StateError('Backend local no respondio en 15 segundos.');
  }

  Future<void> _loadSessionToken() async {
    final payload = _map(
      await _request('GET', '/session', authenticated: false),
    );
    final token = payload['token'];
    if (token is! String || token.isEmpty) {
      throw StateError('El backend no entrego token de sesion.');
    }
    _token = token;
    await _pushSecretsToRunningBackend();
  }

  Future<Map<String, String>> _backendSecretEnvironment() async {
    final result = <String, String>{};
    for (final key in supportedSecretKeys) {
      final value = await _secretStore.read(key);
      if (value != null && value.isNotEmpty) {
        result[key] = value;
      }
    }
    return result;
  }

  Future<void> _pushSecretsToRunningBackend() async {
    if (_token == null) {
      return;
    }
    final secrets = await _backendSecretEnvironment();
    final payload = <String, dynamic>{
      'mercado_publico_ticket': secrets[mercadoPublicoTicketKey],
      'mercadolibre_access_token': secrets[mercadoLibreAccessTokenKey],
      'mercadolibre_refresh_token': secrets[mercadoLibreRefreshTokenKey],
      'mercadolibre_access_token_expires_at':
          secrets[mercadoLibreAccessTokenExpiresAtKey],
      'cmf_api_key': secrets[cmfApiKeyKey],
    }..removeWhere((_, value) => value == null || value == '');
    if (payload.isEmpty) {
      return;
    }
    try {
      await _request('PUT', '/settings', body: payload);
    } catch (error) {
      _appendLog('secret sync failed: ${error.runtimeType}');
    }
  }

  Future<dynamic> _request(
    String method,
    String path, {
    Map<String, String>? query,
    Map<String, dynamic>? body,
    bool authenticated = true,
  }) async {
    final uri = _base.replace(path: path, queryParameters: query);
    final request = await _client.openUrl(method, uri);
    request.headers.set(HttpHeaders.acceptHeader, ContentType.json.mimeType);
    if (authenticated) {
      final token = _token;
      if (token != null) {
        request.headers.set(HttpHeaders.authorizationHeader, 'Bearer $token');
      }
    }
    if (body != null) {
      request.headers.contentType = ContentType.json;
      request.write(jsonEncode(body));
    }
    final response = await request.close();
    final text = await utf8.decoder.bind(response).join();
    if (response.statusCode >= 400) {
      throw ApiException(response.statusCode, text);
    }
    if (text.trim().isEmpty) {
      return <String, dynamic>{};
    }
    return jsonDecode(text);
  }

  Map<String, dynamic> _map(dynamic value) {
    return Map<String, dynamic>.from(value as Map);
  }

  List<Map<String, dynamic>> _list(dynamic value) {
    return (value as List)
        .map((item) => Map<String, dynamic>.from(item as Map))
        .toList();
  }

  void _appendLog(String line) {
    _logs.add(line);
    if (_logs.length > 200) {
      _logs.removeAt(0);
    }
  }

  String _join(String a, String b, [String? c, String? d, String? e]) {
    return [a, b, c, d, e].whereType<String>().join(Platform.pathSeparator);
  }
}
