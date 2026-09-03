import 'package:flutter/material.dart';

import '../core/api/landfinder_api.dart';
import '../features/shell/landfinder_home.dart';
import 'theme.dart';

class LandfinderApp extends StatelessWidget {
  const LandfinderApp({super.key, this.api});

  final LandfinderApi? api;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Landfinder Chile',
      theme: buildLandfinderTheme(),
      home: LandfinderHome(api: api ?? LocalLandfinderApi()),
    );
  }
}
