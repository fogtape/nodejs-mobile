#pragma once

#include <openssl/ssl.h>
#include <cstddef>
#include <cstdint>

#if OPENSSL_VERSION_NUMBER >= 0x40000000L && !defined(OPENSSL_NO_ECH)
#include <openssl/ech.h>
#define NODE_HAVE_ECH 1
#else
#define NODE_HAVE_ECH 0
#endif

namespace node::crypto {

// Supplying an ECHConfigList always requires authenticated ECH. OpenSSL's
// ECH_REQUIRED alert handles rejection; neither TLS nor QUIC may retry with
// cleartext SNI. Verify inside OpenSSL as well as in JS so the outer server
// cannot authenticate retry configs using Node's permissive verify callback.
inline bool ConfigureECH(SSL* ssl, const uint8_t* config, size_t length) {
#if NODE_HAVE_ECH
  if (SSL_set1_ech_config_list(ssl, config, length) != 1 ||
      SSL_set_min_proto_version(ssl, TLS1_3_VERSION) != 1) {
    return false;
  }
  SSL_set_verify(ssl, SSL_VERIFY_PEER, nullptr);
  return true;
#else
  (void)ssl;
  (void)config;
  (void)length;
  return false;
#endif
}

inline int GetECHStatus(SSL* ssl) {
#if NODE_HAVE_ECH
  char* inner = nullptr;
  char* outer = nullptr;
  const int status = SSL_ech_get1_status(ssl, &inner, &outer);
  OPENSSL_free(inner);
  OPENSSL_free(outer);
  return status;
#else
  (void)ssl;
  return -103;  // SSL_ECH_STATUS_NOT_CONFIGURED
#endif
}

}  // namespace node::crypto
