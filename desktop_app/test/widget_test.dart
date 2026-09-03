import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:landfinder_desktop/app/app.dart';
import 'package:landfinder_desktop/src/api.dart';
import 'package:landfinder_desktop/src/secret_store.dart';

void main() {
  testWidgets('renders dashboard with fake backend data', (tester) async {
    tester.view.physicalSize = const Size(1200, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(LandfinderApp(api: _FakeApi()));
    await tester.pumpAndSettle();

    expect(find.text('Landfinder'), findsOneWidget);
    expect(find.text('Dashboard'), findsWidgets);
    expect(find.text('Terrenos'), findsOneWidget);
    expect(find.text('1'), findsAtLeastNWidgets(1));
  });

  testWidgets('selects communes while all regions is active', (tester) async {
    tester.view.physicalSize = const Size(1200, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(LandfinderApp(api: _FakeApi()));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Busqueda'));
    await tester.pumpAndSettle();

    expect(find.text('Todas las regiones'), findsOneWidget);
    expect(find.text('Todas las comunas'), findsOneWidget);

    await tester.tap(find.text('Agregar comuna'));
    await tester.pumpAndSettle();

    expect(find.text('Seleccionar comunas'), findsOneWidget);
    await tester.enterText(find.byType(TextField).last, 'Maipu');
    await tester.pumpAndSettle();
    expect(find.widgetWithText(CheckboxListTile, 'Maipu'), findsOneWidget);

    await tester.tap(find.widgetWithText(CheckboxListTile, 'Maipu'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Aplicar'));
    await tester.pumpAndSettle();

    expect(find.text('Maipu'), findsOneWidget);
  });
}

class _FakeApi implements LandfinderApi {
  @override
  Future<void> start() async {}

  @override
  Future<Map<String, dynamic>> health() async {
    return {'status': 'ok'};
  }

  @override
  Future<List<Map<String, dynamic>>> sources() async {
    return [
      {
        'source_id': 'mercado_publico',
        'source_name': 'Mercado Publico / ChileCompra',
        'source_type': 'public_procurement',
        'strategy': 'official_api',
      },
      {
        'source_id': 'mercadolibre_real_estate',
        'source_name': 'MercadoLibre / PortalInmobiliario',
        'source_type': 'marketplace',
        'strategy': 'official_api',
      },
    ];
  }

  @override
  Future<List<Map<String, dynamic>>> enrichmentSources() async {
    return [
      {
        'source_id': 'cmf_uf',
        'source_name': 'CMF - Conversion UF',
        'source_role': 'EnrichmentSource',
        'source_type': 'monetary',
        'strategy': 'official_api',
      },
      {
        'source_id': 'minvu',
        'source_name': 'IDE MINVU - Informacion territorial',
        'source_role': 'EnrichmentSource',
        'source_type': 'geospatial',
        'strategy': 'arcgis_rest',
      },
    ];
  }

  @override
  Future<List<Map<String, dynamic>>> sourcesHealth() async {
    return [
      {
        'source_id': 'mercado_publico',
        'status': 'DEGRADED',
        'recent_errors': ['Missing ticket'],
      },
      {
        'source_id': 'mercadolibre_real_estate',
        'status': 'ACTIVE',
        'recent_errors': [],
      },
    ];
  }

  @override
  Future<Map<String, dynamic>> sourceAudit(String sourceId) async {
    return {'source_id': sourceId, 'status': 'PARTIAL'};
  }

  @override
  Future<Map<String, dynamic>> regions() async {
    return {
      'items': [
        {
          'code': 'CL-RM',
          'legacy_code': 'RM',
          'name': 'Metropolitana de Santiago',
          'commune_count': 4,
        },
      ],
    };
  }

  @override
  Future<Map<String, dynamic>> communes(String regionCode) async {
    return {
      'region_code': regionCode,
      'items': [
        {'code': '$regionCode-001', 'name': 'Cerrillos'},
        {'code': '$regionCode-002', 'name': 'Maipu'},
        {'code': '$regionCode-003', 'name': 'Pudahuel'},
        {'code': '$regionCode-004', 'name': 'Santiago'},
      ],
    };
  }

  @override
  Future<Map<String, dynamic>> keywordPresets() async {
    return {
      'items': [
        {
          'id': 'BUSQUEDA_TERRENOS_CHILE',
          'name': 'Busqueda terrenos Chile',
          'keywords': ['terreno', 'predio', 'sitio eriazo', 'peladero'],
          'default_mode': 'ANY',
        },
      ],
    };
  }

  @override
  Future<Map<String, dynamic>> settings() async {
    return {
      'has_cmf_api_key': false,
      'has_mercado_publico_ticket': false,
      'has_mercadolibre_access_token': true,
    };
  }

  @override
  Future<Map<String, dynamic>> updateSettings(
    Map<String, dynamic> values,
  ) async {
    return settings();
  }

  @override
  Future<Map<String, bool>> secretStatus() async {
    return {
      mercadoPublicoTicketKey: false,
      cmfApiKeyKey: false,
      mercadoLibreAccessTokenKey: true,
      mercadoLibreRefreshTokenKey: true,
    };
  }

  @override
  Future<void> saveSecret(String key, String value) async {}

  @override
  Future<void> deleteSecret(String key) async {}

  @override
  Future<Map<String, dynamic>> testCredential(String sourceId) async {
    return {
      'source_id': sourceId,
      'status': 'NOT_CONFIGURED',
      'checked_at': DateTime.now().toUtc().toIso8601String(),
      'message': 'No configurado',
    };
  }

  @override
  Future<Map<String, dynamic>> connectMercadoLibre({
    required String clientId,
    required String redirectUri,
    String? clientSecret,
  }) async {
    return {
      'user_id': 1,
      'expires_at': DateTime.now().toUtc().toIso8601String(),
    };
  }

  @override
  Future<bool> refreshMercadoLibreIfNeeded() async {
    return false;
  }

  @override
  Future<Map<String, dynamic>> startSearch(Map<String, dynamic> filters) async {
    return {'search_id': 'job-1', 'status': 'QUEUED'};
  }

  @override
  Future<Map<String, dynamic>> search(String searchId) async {
    return {
      'id': searchId,
      'status': 'COMPLETED',
      'found_count': 1,
      'processed_count': 1,
      'warning_count': 0,
      'error_count': 0,
      'events': [],
    };
  }

  @override
  Future<Map<String, dynamic>> searchSourceRecords(
    String searchId, {
    String? bucket,
    String? q,
    int limit = 500,
  }) async {
    return {
      'items': [
        {
          'source_record_id': 'sr-1',
          'job_id': searchId,
          'source': 'mercado_publico',
          'source_type': 'public_procurement',
          'external_id': '1234-1-LQ26',
          'title': 'Compra terreno',
          'organization': 'SERVIU',
          'automatic_classification': 'LAND_ACQUISITION',
          'automatic_confidence': 0.91,
          'property_id': 'p-1',
          'amount_raw': 'CLP 120000000',
          'amount_type': 'ESTIMATED_AMOUNT',
          'detail_fetched': true,
          'detail_attempts': 1,
          'fields_extracted': ['title', 'amount'],
          'fields_missing': ['surface'],
          'extraction_reasons': {'surface': 'No public area field found'},
        },
      ],
      'total': 1,
      'classifier_distribution': {
        'accepted': 1,
        'possible': 0,
        'rejected': 0,
        'total_analyzed': 1,
      },
    };
  }

  @override
  Future<Map<String, dynamic>> updateManualClassification(
    String sourceRecordId,
    String manualClassification,
  ) async {
    return {
      'source_record_id': sourceRecordId,
      'manual_classification': manualClassification,
      'manual_review_status': 'REVIEWED',
    };
  }

  @override
  Future<Map<String, dynamic>> properties() async {
    return {
      'items': [
        {
          'internal_id': 'p-1',
          'publication_title': 'Terreno urbano',
          'source': 'mercadolibre_real_estate',
          'commune': 'Maipu',
          'gross_area_m2': 10000,
          'asking_price_uf': 2500,
          'price_uf_m2_gross': 0.25,
          'data_quality_score': 70,
          'latitude': -33.5,
          'longitude': -70.7,
          'location_precision': 'APPROXIMATE_PROPERTY',
        },
      ],
      'total': 1,
    };
  }

  @override
  Future<Map<String, dynamic>> propertyTerritory(String propertyId) async {
    return {
      'property_id': propertyId,
      'geometry_metrics': null,
      'evidence': [],
    };
  }

  @override
  Future<Map<String, dynamic>> refreshPropertyTerritory(
    String propertyId, {
    bool forceRefresh = false,
  }) async {
    return propertyTerritory(propertyId);
  }

  @override
  Future<Map<String, dynamic>> minvuServices() async {
    return {'source': 'IDE MINVU ArcGIS REST', 'services': []};
  }

  @override
  Future<Map<String, dynamic>> minvuIptCatalog({String? region}) async {
    return {
      'source': 'IDE MINVU ArcGIS REST',
      'region_hint': region,
      'services': [],
    };
  }

  @override
  Future<Map<String, dynamic>> minvuLayerAudit({
    String? region,
    bool includeFeatureCounts = false,
  }) async {
    return {
      'source': 'IDE MINVU ArcGIS REST',
      'region_hint': region,
      'layers': [],
    };
  }

  @override
  Future<Map<String, dynamic>> exportExcel() async {
    return {'path': 'test.xlsx', 'status': 'created'};
  }

  @override
  List<String> logs() => ['fake backend'];

  @override
  void dispose() {}
}
