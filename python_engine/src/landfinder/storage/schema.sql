PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS property_candidates (
  internal_id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  source_type TEXT NOT NULL,
  external_id TEXT,
  canonical_url TEXT,
  publication_title TEXT,
  publication_date TEXT,
  last_seen TEXT NOT NULL,
  seller_type TEXT NOT NULL,
  broker TEXT,
  listing_status TEXT NOT NULL,
  region TEXT,
  province TEXT,
  commune TEXT,
  locality TEXT,
  original_address TEXT,
  normalized_address TEXT,
  latitude REAL,
  longitude REAL,
  location_precision TEXT NOT NULL,
  location_source TEXT,
  location_method TEXT,
  geocoded_at TEXT,
  geocoding_source TEXT,
  geocoding_confidence REAL NOT NULL DEFAULT 0,
  geometry_status TEXT NOT NULL DEFAULT 'UNKNOWN',
  geometry_source TEXT,
  geometry_type TEXT NOT NULL DEFAULT 'UNKNOWN',
  parcel_geometry TEXT,
  geometry_area_m2 REAL,
  geometry_perimeter_m REAL,
  asking_price_clp NUMERIC,
  asking_price_uf NUMERIC,
  uf_date TEXT,
  uf_rate NUMERIC,
  uf_rate_date TEXT,
  uf_source TEXT,
  uf_retrieved_at TEXT,
  uf_cache_hit INTEGER,
  gross_area_m2 REAL,
  advertised_area_m2 REAL,
  official_area_m2 REAL,
  area_difference_percent REAL,
  price_uf_m2_gross NUMERIC,
  estimated_usable_area_m2 REAL,
  price_uf_m2_usable NUMERIC,
  estimated_net_developable_area_m2 REAL,
  net_developable_ratio REAL,
  usable_price_uf_m2 NUMERIC,
  estimated_dwelling_capacity INTEGER,
  estimated_land_cost_per_dwelling NUMERIC,
  auction_minimum NUMERIC,
  auction_guarantee NUMERIC,
  auction_commission NUMERIC,
  auction_date TEXT,
  data_quality_score INTEGER,
  anomaly_flags_json TEXT NOT NULL DEFAULT '[]',
  territorial_status TEXT NOT NULL DEFAULT 'SIN_INFORMACION_SUFICIENTE',
  territorial_checked_at TEXT,
  territorial_summary_json TEXT NOT NULL DEFAULT '{}',
  candidate_status TEXT NOT NULL DEFAULT 'ACTIVE',
  manual_notes TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_property_location
  ON property_candidates (region, commune, latitude, longitude);

CREATE INDEX IF NOT EXISTS idx_property_price_area
  ON property_candidates (asking_price_uf, gross_area_m2);

CREATE INDEX IF NOT EXISTS idx_property_candidates_location_method
  ON property_candidates (location_method, location_precision);

CREATE TABLE IF NOT EXISTS property_source_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  internal_id TEXT NOT NULL REFERENCES property_candidates(internal_id) ON DELETE CASCADE,
  source TEXT NOT NULL,
  source_type TEXT NOT NULL,
  external_id TEXT,
  canonical_url TEXT,
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL,
  parser_version TEXT,
  raw_payload_json TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_source_external
  ON property_source_records (source, external_id)
  WHERE external_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS source_records (
  source_record_id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL,
  source TEXT NOT NULL,
  source_type TEXT NOT NULL,
  external_id TEXT,
  title TEXT,
  description TEXT,
  organization TEXT,
  organization_region TEXT,
  organization_commune TEXT,
  organization_address TEXT,
  publication_date TEXT,
  closing_date TEXT,
  status TEXT,
  region TEXT,
  commune TEXT,
  property_region TEXT,
  property_commune TEXT,
  property_address TEXT,
  amount NUMERIC,
  currency TEXT,
  amount_raw TEXT,
  amount_type TEXT,
  amount_source TEXT,
  amount_confidence REAL NOT NULL DEFAULT 0,
  surface_raw TEXT,
  surface_m2 REAL,
  surface_source TEXT,
  surface_confidence REAL NOT NULL DEFAULT 0,
  source_url TEXT,
  detail_fetched INTEGER NOT NULL DEFAULT 0,
  detail_attempts INTEGER NOT NULL DEFAULT 0,
  detail_http_status INTEGER,
  fields_extracted_json TEXT NOT NULL DEFAULT '[]',
  fields_missing_json TEXT NOT NULL DEFAULT '[]',
  extraction_reasons_json TEXT NOT NULL DEFAULT '{}',
  data_completeness_score INTEGER NOT NULL DEFAULT 0,
  raw_payload_json TEXT NOT NULL DEFAULT '{}',
  automatic_classification TEXT NOT NULL,
  automatic_confidence REAL NOT NULL DEFAULT 0,
  automatic_score INTEGER NOT NULL DEFAULT 0,
  classification_reason TEXT,
  positive_terms_json TEXT NOT NULL DEFAULT '[]',
  negative_terms_json TEXT NOT NULL DEFAULT '[]',
  rules_triggered_json TEXT NOT NULL DEFAULT '[]',
  manual_classification TEXT NOT NULL DEFAULT 'UNREVIEWED',
  manual_review_status TEXT NOT NULL DEFAULT 'UNREVIEWED',
  property_id TEXT REFERENCES property_candidates(internal_id) ON DELETE SET NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_source_records_job_classification
  ON source_records (job_id, automatic_classification, manual_classification);

CREATE INDEX IF NOT EXISTS idx_source_records_source_external
  ON source_records (source, external_id);

CREATE TABLE IF NOT EXISTS classifier_feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_record_id TEXT NOT NULL REFERENCES source_records(source_record_id) ON DELETE CASCADE,
  job_id TEXT NOT NULL,
  automatic_classification TEXT NOT NULL,
  automatic_confidence REAL NOT NULL DEFAULT 0,
  automatic_score INTEGER NOT NULL DEFAULT 0,
  manual_classification TEXT NOT NULL,
  positive_terms_json TEXT NOT NULL DEFAULT '[]',
  negative_terms_json TEXT NOT NULL DEFAULT '[]',
  classification_reason TEXT,
  reviewed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS canonical_properties (
  canonical_id TEXT PRIMARY KEY,
  primary_internal_id TEXT NOT NULL REFERENCES property_candidates(internal_id),
  source_count INTEGER NOT NULL DEFAULT 1,
  duplicate_confidence REAL NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS canonical_property_sources (
  canonical_id TEXT NOT NULL REFERENCES canonical_properties(canonical_id) ON DELETE CASCADE,
  internal_id TEXT NOT NULL REFERENCES property_candidates(internal_id) ON DELETE CASCADE,
  match_reason_json TEXT NOT NULL DEFAULT '[]',
  match_score REAL NOT NULL DEFAULT 0,
  PRIMARY KEY (canonical_id, internal_id)
);

CREATE TABLE IF NOT EXISTS evidence_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  internal_id TEXT NOT NULL REFERENCES property_candidates(internal_id) ON DELETE CASCADE,
  property_id TEXT,
  category TEXT,
  field TEXT NOT NULL,
  value TEXT,
  source_name TEXT,
  source_url TEXT,
  layer_name TEXT,
  source_record_id TEXT,
  raw_metadata TEXT NOT NULL DEFAULT '{}',
  raw_value TEXT,
  normalized_value TEXT,
  source TEXT NOT NULL,
  url TEXT,
  retrieved_at TEXT NOT NULL,
  method TEXT,
  parser_version TEXT,
  rule_version TEXT,
  confidence REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS data_provenance (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  property_id TEXT NOT NULL REFERENCES property_candidates(internal_id) ON DELETE CASCADE,
  field_name TEXT NOT NULL,
  value TEXT,
  source_id TEXT NOT NULL,
  source_type TEXT NOT NULL,
  method TEXT,
  retrieved_at TEXT NOT NULL,
  confidence REAL NOT NULL DEFAULT 0,
  source_url TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_data_provenance_field
  ON data_provenance (property_id, field_name, source_id, method);

CREATE TABLE IF NOT EXISTS geometry_metrics (
  internal_id TEXT PRIMARY KEY REFERENCES property_candidates(internal_id) ON DELETE CASCADE,
  geometry_status TEXT NOT NULL DEFAULT 'UNKNOWN',
  geometry_type TEXT NOT NULL DEFAULT 'UNKNOWN',
  geometry_source TEXT,
  geometry_retrieved_at TEXT,
  geometry_confidence REAL NOT NULL DEFAULT 0,
  parcel_geometry TEXT,
  polygon_geojson TEXT,
  polygon_wkb BLOB,
  official_area_m2 REAL,
  area_difference_percent REAL,
  geometric_area_m2 REAL,
  perimeter_m REAL,
  estimated_width_m REAL,
  estimated_depth_m REAL,
  width_depth_ratio REAL,
  verified_street_frontage_m REAL,
  estimated_main_frontage_m REAL,
  secondary_frontages_json TEXT NOT NULL DEFAULT '[]',
  approximate_depth_m REAL,
  frontage_depth_ratio REAL,
  public_road_frontage_count INTEGER,
  compactness_index REAL,
  elongation REAL,
  irregularity_index REAL,
  orientation_degrees REAL,
  bounding_box_json TEXT,
  centroid_latitude REAL,
  centroid_longitude REAL,
  shape_quality_score INTEGER,
  shape_warnings_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS geospatial_cache (
  cache_key TEXT PRIMARY KEY,
  service_url TEXT NOT NULL,
  layer_id TEXT NOT NULL,
  geometry_hash TEXT NOT NULL,
  query_hash TEXT NOT NULL,
  spatial_reference TEXT NOT NULL,
  response_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS geocoding_cache (
  cache_key TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  query_text TEXT NOT NULL,
  normalized_query TEXT NOT NULL,
  request_json TEXT NOT NULL DEFAULT '{}',
  response_json TEXT NOT NULL DEFAULT '{}',
  latitude REAL,
  longitude REAL,
  display_name TEXT,
  location_precision TEXT NOT NULL DEFAULT 'UNKNOWN',
  location_method TEXT NOT NULL,
  confidence REAL NOT NULL DEFAULT 0,
  source_url TEXT,
  created_at TEXT NOT NULL,
  last_used_at TEXT NOT NULL,
  expires_at TEXT
);

CREATE TABLE IF NOT EXISTS property_location_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  internal_id TEXT NOT NULL REFERENCES property_candidates(internal_id) ON DELETE CASCADE,
  latitude REAL,
  longitude REAL,
  location_source TEXT,
  location_method TEXT NOT NULL,
  location_precision TEXT NOT NULL DEFAULT 'UNKNOWN',
  location_confidence REAL NOT NULL DEFAULT 0,
  address TEXT,
  region TEXT,
  commune TEXT,
  raw_result_json TEXT NOT NULL DEFAULT '{}',
  assigned_by TEXT NOT NULL DEFAULT 'system',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS minvu_layers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  provider TEXT NOT NULL,
  service_name TEXT NOT NULL,
  layer_name TEXT NOT NULL,
  layer_id INTEGER NOT NULL,
  endpoint TEXT NOT NULL,
  geometry_type TEXT,
  spatial_reference TEXT NOT NULL DEFAULT '{}',
  fields_json TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL,
  last_checked TEXT NOT NULL,
  raw_metadata_json TEXT NOT NULL DEFAULT '{}',
  UNIQUE(provider, endpoint, layer_id)
);

CREATE TABLE IF NOT EXISTS territorial_criteria (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  internal_id TEXT NOT NULL REFERENCES property_candidates(internal_id) ON DELETE CASCADE,
  criterion_key TEXT NOT NULL,
  criterion_label TEXT NOT NULL,
  result TEXT NOT NULL,
  value TEXT,
  source TEXT,
  endpoint TEXT,
  layer_name TEXT,
  checked_at TEXT NOT NULL,
  evidence_json TEXT NOT NULL DEFAULT '{}',
  confidence REAL NOT NULL DEFAULT 0,
  observation TEXT,
  UNIQUE(internal_id, criterion_key, source, layer_name)
);

CREATE INDEX IF NOT EXISTS idx_territorial_criteria_property
  ON territorial_criteria (internal_id, checked_at);

CREATE TABLE IF NOT EXISTS net_developable_exclusions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  internal_id TEXT NOT NULL REFERENCES property_candidates(internal_id) ON DELETE CASCADE,
  layer TEXT NOT NULL,
  source TEXT NOT NULL,
  retrieved_at TEXT NOT NULL,
  intersected_area_m2 REAL NOT NULL,
  rule_applied TEXT NOT NULL,
  confidence REAL NOT NULL,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS cadastral_info (
  internal_id TEXT PRIMARY KEY REFERENCES property_candidates(internal_id) ON DELETE CASCADE,
  assessment_role TEXT,
  cadastral_area_m2 REAL,
  land_use TEXT,
  fiscal_valuation_clp NUMERIC,
  taxable_valuation_clp NUMERIC,
  exempt_valuation_clp NUMERIC,
  information_date TEXT,
  source TEXT,
  confidence REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS urban_facts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  internal_id TEXT NOT NULL REFERENCES property_candidates(internal_id) ON DELETE CASCADE,
  key TEXT NOT NULL,
  value_json TEXT,
  source TEXT NOT NULL,
  source_document TEXT,
  effective_date TEXT,
  retrieved_at TEXT NOT NULL,
  confidence REAL NOT NULL DEFAULT 0,
  manual_review_required INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cip_status (
  internal_id TEXT PRIMARY KEY REFERENCES property_candidates(internal_id) ON DELETE CASCADE,
  status TEXT NOT NULL,
  document_id TEXT,
  source_url TEXT,
  uploaded_at TEXT,
  parsed_at TEXT,
  pending_fields_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS risk_assessments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  internal_id TEXT NOT NULL REFERENCES property_candidates(internal_id) ON DELETE CASCADE,
  type TEXT NOT NULL,
  severity TEXT,
  status TEXT NOT NULL,
  intersected_area_m2 REAL,
  distance_m REAL,
  source TEXT NOT NULL,
  confidence REAL NOT NULL DEFAULT 0,
  evidence_url TEXT,
  retrieved_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS infrastructure_assessments (
  internal_id TEXT PRIMARY KEY REFERENCES property_candidates(internal_id) ON DELETE CASCADE,
  sanitary_operational_area TEXT,
  water_network_distance_m REAL,
  sewer_network_distance_m REAL,
  electricity_distance_m REAL,
  road_access_distance_m REAL,
  formal_feasibility_available INTEGER,
  notes_json TEXT NOT NULL DEFAULT '[]',
  confidence REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS accessibility_metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  internal_id TEXT NOT NULL REFERENCES property_candidates(internal_id) ON DELETE CASCADE,
  category TEXT NOT NULL,
  nearest_name TEXT,
  straight_line_distance_m REAL,
  walking_network_distance_m REAL,
  methodology TEXT NOT NULL,
  source TEXT NOT NULL,
  confidence REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS rule_evaluations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  internal_id TEXT NOT NULL REFERENCES property_candidates(internal_id) ON DELETE CASCADE,
  rule_id TEXT NOT NULL,
  program TEXT NOT NULL,
  year INTEGER NOT NULL,
  call TEXT,
  status TEXT NOT NULL,
  severity TEXT NOT NULL,
  description TEXT NOT NULL,
  legal_source TEXT,
  effective_date TEXT,
  automatic INTEGER NOT NULL,
  checked_at TEXT NOT NULL,
  evidence_json TEXT NOT NULL DEFAULT '[]',
  notes TEXT
);

CREATE TABLE IF NOT EXISTS compatibility_assessments (
  internal_id TEXT NOT NULL REFERENCES property_candidates(internal_id) ON DELETE CASCADE,
  program TEXT NOT NULL,
  status TEXT NOT NULL,
  confidence REAL NOT NULL DEFAULT 0,
  reasons_json TEXT NOT NULL DEFAULT '[]',
  passed_rules_json TEXT NOT NULL DEFAULT '[]',
  failed_rules_json TEXT NOT NULL DEFAULT '[]',
  unknown_rules_json TEXT NOT NULL DEFAULT '[]',
  pending_documents_json TEXT NOT NULL DEFAULT '[]',
  PRIMARY KEY (internal_id, program)
);

CREATE TABLE IF NOT EXISTS documents (
  document_id TEXT PRIMARY KEY,
  internal_id TEXT NOT NULL REFERENCES property_candidates(internal_id) ON DELETE CASCADE,
  document_type TEXT NOT NULL,
  original_filename TEXT NOT NULL,
  stored_path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  uploaded_at TEXT NOT NULL,
  source TEXT NOT NULL,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS images (
  image_id TEXT PRIMARY KEY,
  internal_id TEXT NOT NULL REFERENCES property_candidates(internal_id) ON DELETE CASCADE,
  source_url TEXT,
  original_path TEXT,
  preview_path TEXT,
  sha256 TEXT,
  perceptual_hash TEXT,
  mime_type TEXT,
  retrieved_at TEXT,
  allowed_to_download INTEGER
);

CREATE TABLE IF NOT EXISTS price_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  internal_id TEXT NOT NULL REFERENCES property_candidates(internal_id) ON DELETE CASCADE,
  observed_at TEXT NOT NULL,
  asking_price_clp NUMERIC,
  asking_price_uf NUMERIC,
  uf_date TEXT,
  source TEXT NOT NULL,
  evidence_url TEXT
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
  run_id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  query_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  error_summary TEXT
);

CREATE TABLE IF NOT EXISTS pipeline_stage_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL REFERENCES pipeline_runs(run_id) ON DELETE CASCADE,
  stage TEXT NOT NULL,
  status TEXT NOT NULL,
  processed INTEGER NOT NULL DEFAULT 0,
  total INTEGER,
  started_at TEXT,
  finished_at TEXT,
  warnings_json TEXT NOT NULL DEFAULT '[]',
  errors_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS connector_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT REFERENCES pipeline_runs(run_id) ON DELETE SET NULL,
  source_id TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  found_count INTEGER NOT NULL DEFAULT 0,
  latency_ms INTEGER,
  parser_version TEXT NOT NULL,
  errors_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS source_run_status (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL,
  source_id TEXT NOT NULL,
  source_type TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 0,
  configured INTEGER NOT NULL DEFAULT 0,
  attempted INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  records_received INTEGER NOT NULL DEFAULT 0,
  records_accepted INTEGER NOT NULL DEFAULT 0,
  records_rejected INTEGER NOT NULL DEFAULT 0,
  warnings TEXT NOT NULL DEFAULT '[]',
  errors TEXT NOT NULL DEFAULT '[]',
  queries_json TEXT NOT NULL DEFAULT '[]'
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_source_run_status_job_source
  ON source_run_status (job_id, source_id);

CREATE TABLE IF NOT EXISTS source_health (
  source_id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  last_success_at TEXT,
  recent_errors_json TEXT NOT NULL DEFAULT '[]',
  found_count INTEGER NOT NULL DEFAULT 0,
  selector_or_api TEXT,
  latency_ms INTEGER,
  parser_version TEXT NOT NULL,
  checked_at TEXT NOT NULL
);
