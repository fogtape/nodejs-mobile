'use strict';

const common = require('../common');
if (!common.hasCrypto) common.skip('missing crypto');
const assert = require('assert');
const tls = require('tls');
const fixtures = require('../common/fixtures');
const { generateKeyPairSync } = require('crypto');

assert.strictEqual(typeof tls.ECH_SUPPORTED, 'boolean');
assert.strictEqual(typeof tls.TLSSocket.prototype.getECHStatus, 'function');
if (process.platform === 'android' && /^4\./.test(process.versions.openssl)) {
  assert.strictEqual(tls.ECH_SUPPORTED, true);
  assert.strictEqual(process.features.quic, true);
}
assert.throws(() => tls.connect({ echConfigList: 'invalid' }),
              { code: 'ERR_INVALID_ARG_TYPE' });
assert.throws(() => tls.connect({ echConfigList: Buffer.alloc(0) }),
              { code: 'ERR_INVALID_ARG_VALUE' });

if (!tls.ECH_SUPPORTED) {
  assert.throws(() => tls.connect({
    servername: 'localhost', echConfigList: Buffer.from([0, 0]),
  }), { code: 'ERR_INVALID_ARG_VALUE' });
} else {
  // RFC 9849 ECHConfigList with a fresh public key. The ordinary local TLS
  // server has no ECH key: the client MUST fail without sending application
  // bytes, even when the caller queues a write before secureConnect.
  const { publicKey } = generateKeyPairSync('x25519');
  const key = publicKey.export({ type: 'spki', format: 'der' }).subarray(-32);
  const name = Buffer.from('localhost');
  const content = Buffer.concat([
    Buffer.from([1, 0, 32, 0, 32]), key,
    Buffer.from([0, 4, 0, 1, 0, 1, 0, name.length]), name,
    Buffer.from([0, 0]),
  ]);
  const config = Buffer.concat([
    Buffer.from([0, content.length + 4, 0xfe, 0x0d, 0, content.length]), content,
  ]);
  assert.throws(() => tls.connect({ servername: 'localhost',
    rejectUnauthorized: false, echConfigList: config }),
  { code: 'ERR_INVALID_ARG_VALUE' });
  const server = tls.createServer({
    key: fixtures.readKey('agent1-key.pem'),
    cert: fixtures.readKey('agent1-cert.pem'),
  }, (socket) => {
    socket.on('data', common.mustNotCall('ECH rejection leaked application data'));
    socket.on('error', () => {});
  });
  server.on('tlsClientError', () => {});
  server.listen(0, '127.0.0.1', common.mustCall(() => {
    const socket = tls.connect({
      host: '127.0.0.1', port: server.address().port, servername: 'localhost',
      ca: fixtures.readKey('agent1-cert.pem'), echConfigList: config,
    }, common.mustNotCall('ECH rejection emitted secureConnect'));
    socket.write('must stay encrypted to the intended ECH server', () => {});
    socket.once('error', common.mustCall(() => server.close()));
    socket.setTimeout(5000, () => socket.destroy(new Error('ECH test timed out')));
  }));
}
