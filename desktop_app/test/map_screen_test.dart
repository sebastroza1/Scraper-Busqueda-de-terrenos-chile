import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:landfinder_desktop/features/map/map_screen.dart';

void main() {
  testWidgets('renders map controls and selected property popup', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1200, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: LandfinderMapScreen(
            properties: const [
              {
                'internal_id': 'p-1',
                'publication_title': 'Terreno urbano',
                'source': 'mercadolibre_real_estate',
                'commune': 'Santiago',
                'gross_area_m2': 1000,
                'asking_price_uf': 2500,
                'latitude': -33.4489,
                'longitude': -70.6693,
                'location_precision': 'APPROXIMATE_PROPERTY',
              },
            ],
            selectedProperty: const {
              'internal_id': 'p-1',
              'publication_title': 'Terreno urbano',
              'source': 'mercadolibre_real_estate',
              'commune': 'Santiago',
              'gross_area_m2': 1000,
              'asking_price_uf': 2500,
              'latitude': -33.4489,
              'longitude': -70.6693,
              'location_precision': 'APPROXIMATE_PROPERTY',
            },
            territoryByProperty: const {},
            showLandLayer: true,
            showUrbanLimitLayer: true,
            showRiskLayer: true,
            showZoningLayer: true,
            refreshingTerritory: false,
            onLandLayerChanged: (_) {},
            onUrbanLimitLayerChanged: (_) {},
            onRiskLayerChanged: (_) {},
            onZoningLayerChanged: (_) {},
            onSelectProperty: (_) {},
            onRefreshTerritory: () {},
          ),
        ),
      ),
    );
    await tester.pump();

    expect(find.text('Terrenos'), findsOneWidget);
    expect(find.text('Limites urbanos'), findsOneWidget);
    expect(find.text('Areas de riesgo'), findsOneWidget);
    expect(find.text('Zonificacion'), findsOneWidget);
    expect(find.text('Terreno urbano'), findsOneWidget);
    expect(find.text('(c) OpenStreetMap contributors'), findsOneWidget);
  });
}
