#include "secret_store.h"

#include <flutter/encodable_value.h>
#include <flutter/method_channel.h>
#include <flutter/standard_method_codec.h>
#include <windows.h>
#include <wincred.h>

#include <memory>
#include <string>
#include <vector>

#include "utils.h"

namespace {

constexpr wchar_t kTargetPrefix[] = L"LandfinderChile:";
constexpr char kChannelName[] = "landfinder/secret_store";

std::unique_ptr<flutter::MethodChannel<flutter::EncodableValue>> g_channel;

std::wstring Utf16FromUtf8(const std::string& value) {
  if (value.empty()) {
    return std::wstring();
  }
  int length = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, value.data(),
                                  static_cast<int>(value.size()), nullptr, 0);
  if (length <= 0) {
    return std::wstring();
  }
  std::wstring result(length, L'\0');
  MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, value.data(),
                      static_cast<int>(value.size()), result.data(), length);
  return result;
}

std::wstring TargetForKey(const std::string& key) {
  return std::wstring(kTargetPrefix) + Utf16FromUtf8(key);
}

const std::string* ReadStringArg(const flutter::EncodableMap& args,
                                 const char* name) {
  auto iterator = args.find(flutter::EncodableValue(name));
  if (iterator == args.end()) {
    return nullptr;
  }
  return std::get_if<std::string>(&iterator->second);
}

void WriteSecret(const std::string& key, const std::string& value,
                 std::unique_ptr<flutter::MethodResult<flutter::EncodableValue>> result) {
  std::wstring target = TargetForKey(key);
  std::wstring username = L"Landfinder";
  std::vector<BYTE> secret(value.begin(), value.end());

  CREDENTIALW credential = {};
  credential.Type = CRED_TYPE_GENERIC;
  credential.TargetName = const_cast<LPWSTR>(target.c_str());
  credential.UserName = const_cast<LPWSTR>(username.c_str());
  credential.CredentialBlobSize = static_cast<DWORD>(secret.size());
  credential.CredentialBlob = secret.empty() ? nullptr : secret.data();
  credential.Persist = CRED_PERSIST_LOCAL_MACHINE;

  if (!CredWriteW(&credential, 0)) {
    result->Error("cred_write_failed", "Windows Credential Manager rejected the secret.");
    return;
  }
  result->Success(flutter::EncodableValue(true));
}

void ReadSecret(const std::string& key,
                std::unique_ptr<flutter::MethodResult<flutter::EncodableValue>> result) {
  std::wstring target = TargetForKey(key);
  PCREDENTIALW credential = nullptr;
  if (!CredReadW(target.c_str(), CRED_TYPE_GENERIC, 0, &credential)) {
    result->Success();
    return;
  }

  std::string value;
  if (credential->CredentialBlob != nullptr && credential->CredentialBlobSize > 0) {
    value.assign(reinterpret_cast<char*>(credential->CredentialBlob),
                 reinterpret_cast<char*>(credential->CredentialBlob) +
                     credential->CredentialBlobSize);
  }
  CredFree(credential);
  result->Success(flutter::EncodableValue(value));
}

void DeleteSecret(const std::string& key,
                  std::unique_ptr<flutter::MethodResult<flutter::EncodableValue>> result) {
  std::wstring target = TargetForKey(key);
  CredDeleteW(target.c_str(), CRED_TYPE_GENERIC, 0);
  result->Success(flutter::EncodableValue(true));
}

}  // namespace

void RegisterSecretStoreChannel(flutter::BinaryMessenger* messenger) {
  g_channel = std::make_unique<flutter::MethodChannel<flutter::EncodableValue>>(
      messenger, kChannelName, &flutter::StandardMethodCodec::GetInstance());

  g_channel->SetMethodCallHandler(
      [](const flutter::MethodCall<flutter::EncodableValue>& call,
         std::unique_ptr<flutter::MethodResult<flutter::EncodableValue>> result) {
        const auto* args = std::get_if<flutter::EncodableMap>(call.arguments());
        if (args == nullptr) {
          result->Error("invalid_args", "Expected map arguments.");
          return;
        }
        const std::string* key = ReadStringArg(*args, "key");
        if (key == nullptr || key->empty()) {
          result->Error("invalid_key", "A non-empty key is required.");
          return;
        }

        if (call.method_name() == "write") {
          const std::string* value = ReadStringArg(*args, "value");
          if (value == nullptr) {
            result->Error("invalid_value", "A string value is required.");
            return;
          }
          WriteSecret(*key, *value, std::move(result));
          return;
        }
        if (call.method_name() == "read") {
          ReadSecret(*key, std::move(result));
          return;
        }
        if (call.method_name() == "delete") {
          DeleteSecret(*key, std::move(result));
          return;
        }
        result->NotImplemented();
      });
}
