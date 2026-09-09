import 'package:flutter/material.dart';

enum AppSection {
  dashboard('Dashboard', Icons.dashboard_outlined),
  search('Busqueda', Icons.manage_search_outlined),
  mercadoLibreImport('Importar Mercado Libre', Icons.add_link_outlined),
  results('Resultados', Icons.table_rows_outlined),
  map('Mapa', Icons.map_outlined),
  sources('Fuentes', Icons.hub_outlined),
  exports('Exportar', Icons.file_download_outlined),
  settings('Config', Icons.settings_outlined);

  const AppSection(this.label, this.icon);

  final String label;
  final IconData icon;
}
