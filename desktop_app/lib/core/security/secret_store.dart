import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';

const mercadoPublicoTicketKey = 'MERCADO_PUBLICO_TICKET';
const cmfApiKeyKey = 'CMF_API_KEY';
const mercadoLibreClientIdKey = 'MERCADOLIBRE_CLIENT_ID';
const mercadoLibreClientSecretKey = 'MERCADOLIBRE_CLIENT_SECRET';
const mercadoLibreRedirectUriKey = 'MERCADOLIBRE_REDIRECT_URI';
const mercadoLibreAccessTokenKey = 'MERCADOLIBRE_ACCESS_TOKEN';
const mercadoLibreRefreshTokenKey = 'MERCADOLIBRE_REFRESH_TOKEN';
const mercadoLibreAccessTokenExpiresAtKey =
    'MERCADOLIBRE_ACCESS_TOKEN_EXPIRES_AT';

const supportedSecretKeys = [
  mercadoPublicoTicketKey,
  cmfApiKeyKey,
  mercadoLibreClientIdKey,
  mercadoLibreClientSecretKey,
  mercadoLibreRedirectUriKey,
  mercadoLibreAccessTokenKey,
  mercadoLibreRefreshTokenKey,
  mercadoLibreAccessTokenExpiresAtKey,
];

abstract class SecretStore {
  Future<String?> read(String key);
  Future<void> write(String key, String value);
  Future<void> delete(String key);

  Future<bool> has(String key) async {
    final value = await read(key);
    return value != null && value.isNotEmpty;
  }

  Future<Map<String, bool>> status(Iterable<String> keys) async {
    final result = <String, bool>{};
    for (final key in keys) {
      result[key] = await has(key);
    }
    return result;
  }

  static SecretStore create() {
    if (Platform.isWindows) {
      return ChainedSecretStore([
        WindowsCredentialSecretStore(),
        DevelopmentFileSecretStore(),
      ]);
    }
    return DevelopmentFileSecretStore();
  }
}

class WindowsCredentialSecretStore extends SecretStore {
  static const MethodChannel _channel = MethodChannel(
    'landfinder/secret_store',
  );

  @override
  Future<String?> read(String key) async {
    final value = await _channel.invokeMethod<String>('read', {'key': key});
    return value == null || value.isEmpty ? null : value;
  }

  @override
  Future<void> write(String key, String value) async {
    await _channel.invokeMethod<bool>('write', {'key': key, 'value': value});
  }

  @override
  Future<void> delete(String key) async {
    await _channel.invokeMethod<bool>('delete', {'key': key});
  }
}

class DevelopmentFileSecretStore extends SecretStore {
  DevelopmentFileSecretStore({File? file}) : _file = file ?? _defaultFile();

  final File _file;

  @override
  Future<String?> read(String key) async {
    final values = await _readAll();
    final value = values[key];
    return value == null || value.isEmpty ? null : value;
  }

  @override
  Future<void> write(String key, String value) async {
    final values = await _readAll();
    values[key] = value;
    await _file.parent.create(recursive: true);
    await _file.writeAsString(jsonEncode(values), flush: true);
  }

  @override
  Future<void> delete(String key) async {
    final values = await _readAll();
    values.remove(key);
    await _file.parent.create(recursive: true);
    await _file.writeAsString(jsonEncode(values), flush: true);
  }

  Future<Map<String, String>> _readAll() async {
    if (!await _file.exists()) {
      return {};
    }
    final text = await _file.readAsString();
    if (text.trim().isEmpty) {
      return {};
    }
    final decoded = jsonDecode(text) as Map;
    return decoded.map(
      (key, value) => MapEntry(key.toString(), value.toString()),
    );
  }

  static File _defaultFile() {
    final root =
        Platform.environment['LOCALAPPDATA'] ??
        Platform.environment['APPDATA'] ??
        Directory.systemTemp.path;
    return File(
      '$root${Platform.pathSeparator}Landfinder${Platform.pathSeparator}dev_secrets.json',
    );
  }
}

class ChainedSecretStore extends SecretStore {
  ChainedSecretStore(this._stores);

  final List<SecretStore> _stores;

  @override
  Future<String?> read(String key) async {
    for (final store in _stores) {
      try {
        final value = await store.read(key);
        if (value != null && value.isNotEmpty) {
          return value;
        }
      } catch (_) {
        continue;
      }
    }
    return null;
  }

  @override
  Future<void> write(String key, String value) async {
    Object? lastError;
    for (final store in _stores) {
      try {
        await store.write(key, value);
        return;
      } catch (error) {
        lastError = error;
      }
    }
    throw StateError('No secret store accepted the value: $lastError');
  }

  @override
  Future<void> delete(String key) async {
    for (final store in _stores) {
      try {
        await store.delete(key);
      } catch (_) {
        continue;
      }
    }
  }
}

String maskSecretStatus(bool configured) {
  return configured ? 'Configurado' : 'No configurado';
}
