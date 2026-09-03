import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:crypto/crypto.dart';

import 'secret_store.dart';

class MercadoLibreOAuthResult {
  MercadoLibreOAuthResult({
    required this.userId,
    required this.expiresAt,
    required this.scope,
  });

  final String userId;
  final DateTime expiresAt;
  final String scope;

  Map<String, dynamic> toJson() {
    return {
      'user_id': userId,
      'expires_at': expiresAt.toIso8601String(),
      'scope': scope,
    };
  }
}

class MercadoLibreOAuthException implements Exception {
  MercadoLibreOAuthException(this.message);

  final String message;

  @override
  String toString() => message;
}

class MercadoLibreOAuthFlow {
  MercadoLibreOAuthFlow(this.secretStore);

  final SecretStore secretStore;
  final HttpClient _client = HttpClient();

  Future<MercadoLibreOAuthResult> authorize({
    required String clientId,
    required String redirectUri,
    String? clientSecret,
    Duration timeout = const Duration(minutes: 3),
  }) async {
    final parsedRedirect = Uri.parse(redirectUri);
    if (!_isLocalRedirect(parsedRedirect)) {
      throw MercadoLibreOAuthException(
        'La captura automatica requiere redirect_uri local http://127.0.0.1:<puerto>/... registrado exactamente en MercadoLibre.',
      );
    }

    final state = _randomUrlSafe(32);
    final verifier = _randomUrlSafe(64);
    final challenge = _codeChallenge(verifier);
    final server = await HttpServer.bind(
      parsedRedirect.host,
      parsedRedirect.hasPort ? parsedRedirect.port : 80,
      shared: true,
    );
    try {
      final authorizationUrl =
          Uri.https('auth.mercadolibre.cl', '/authorization', {
            'response_type': 'code',
            'client_id': clientId,
            'redirect_uri': redirectUri,
            'state': state,
            'code_challenge': challenge,
            'code_challenge_method': 'S256',
          });
      await _openBrowser(authorizationUrl);
      final code = await _waitForCode(
        server,
        parsedRedirect.path,
        state,
        timeout,
      );
      return await exchangeCode(
        clientId: clientId,
        clientSecret: clientSecret,
        redirectUri: redirectUri,
        code: code,
        codeVerifier: verifier,
      );
    } finally {
      await server.close(force: true);
    }
  }

  Future<MercadoLibreOAuthResult> exchangeCode({
    required String clientId,
    required String redirectUri,
    required String code,
    required String codeVerifier,
    String? clientSecret,
  }) async {
    final payload = <String, String>{
      'grant_type': 'authorization_code',
      'client_id': clientId,
      'code': code,
      'redirect_uri': redirectUri,
      'code_verifier': codeVerifier,
    };
    if (clientSecret != null && clientSecret.isNotEmpty) {
      payload['client_secret'] = clientSecret;
    }
    return _tokenRequest(payload);
  }

  Future<MercadoLibreOAuthResult> refresh({
    required String clientId,
    required String refreshToken,
    String? clientSecret,
  }) async {
    final payload = <String, String>{
      'grant_type': 'refresh_token',
      'client_id': clientId,
      'refresh_token': refreshToken,
    };
    if (clientSecret != null && clientSecret.isNotEmpty) {
      payload['client_secret'] = clientSecret;
    }
    return _tokenRequest(payload);
  }

  Future<MercadoLibreOAuthResult> _tokenRequest(
    Map<String, String> payload,
  ) async {
    final request = await _client.postUrl(
      Uri.https('api.mercadolibre.com', '/oauth/token'),
    );
    request.headers.contentType = ContentType(
      'application',
      'x-www-form-urlencoded',
    );
    request.headers.set(HttpHeaders.acceptHeader, ContentType.json.mimeType);
    request.write(
      payload.entries
          .map(
            (entry) =>
                '${Uri.encodeQueryComponent(entry.key)}=${Uri.encodeQueryComponent(entry.value)}',
          )
          .join('&'),
    );
    final response = await request.close();
    final text = await utf8.decoder.bind(response).join();
    final decoded = text.trim().isEmpty
        ? <String, dynamic>{}
        : jsonDecode(text) as Map;
    if (response.statusCode == 401 || response.statusCode == 403) {
      throw MercadoLibreOAuthException(
        'MercadoLibre rechazo OAuth (${response.statusCode}). Verifica app, scopes, redirect_uri y usuario administrador.',
      );
    }
    if (response.statusCode >= 400) {
      throw MercadoLibreOAuthException(
        'OAuth MercadoLibre fallo (${response.statusCode}): $text',
      );
    }

    final accessToken = decoded['access_token']?.toString();
    final refreshToken = decoded['refresh_token']?.toString();
    final expiresIn =
        int.tryParse(decoded['expires_in']?.toString() ?? '') ?? 0;
    if (accessToken == null || refreshToken == null || expiresIn <= 0) {
      throw MercadoLibreOAuthException(
        'MercadoLibre no entrego tokens completos.',
      );
    }
    final expiresAt = DateTime.now().toUtc().add(Duration(seconds: expiresIn));
    await secretStore.write(mercadoLibreAccessTokenKey, accessToken);
    await secretStore.write(mercadoLibreRefreshTokenKey, refreshToken);
    await secretStore.write(
      mercadoLibreAccessTokenExpiresAtKey,
      expiresAt.toIso8601String(),
    );

    return MercadoLibreOAuthResult(
      userId: decoded['user_id']?.toString() ?? '',
      expiresAt: expiresAt,
      scope: decoded['scope']?.toString() ?? '',
    );
  }

  Future<String> _waitForCode(
    HttpServer server,
    String expectedPath,
    String expectedState,
    Duration timeout,
  ) async {
    final request = await server.first.timeout(timeout);
    final response = request.response;
    final code = request.uri.queryParameters['code'];
    final state = request.uri.queryParameters['state'];
    final error = request.uri.queryParameters['error'];
    if (request.uri.path != expectedPath ||
        error != null ||
        state != expectedState ||
        code == null) {
      response.statusCode = HttpStatus.badRequest;
      response.write('No se pudo completar la autorizacion de MercadoLibre.');
      await response.close();
      throw MercadoLibreOAuthException('Callback OAuth invalido o rechazado.');
    }
    response.headers.contentType = ContentType.html;
    response.write(
      '<html><body><h1>MercadoLibre conectado</h1><p>Puedes volver a Landfinder.</p></body></html>',
    );
    await response.close();
    return code;
  }

  Future<void> _openBrowser(Uri url) async {
    if (Platform.isWindows) {
      await Process.run('rundll32.exe', [
        'url.dll,FileProtocolHandler',
        url.toString(),
      ]);
      return;
    }
    if (Platform.isMacOS) {
      await Process.run('open', [url.toString()]);
      return;
    }
    await Process.run('xdg-open', [url.toString()]);
  }

  bool _isLocalRedirect(Uri uri) {
    return uri.scheme == 'http' &&
        (uri.host == '127.0.0.1' || uri.host == 'localhost');
  }

  String _randomUrlSafe(int bytes) {
    final random = Random.secure();
    final values = List<int>.generate(bytes, (_) => random.nextInt(256));
    return base64UrlEncode(values).replaceAll('=', '');
  }

  String _codeChallenge(String verifier) {
    return base64UrlEncode(
      sha256.convert(utf8.encode(verifier)).bytes,
    ).replaceAll('=', '');
  }
}
