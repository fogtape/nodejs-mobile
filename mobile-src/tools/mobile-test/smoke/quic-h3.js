'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createPrivateKey } = require('node:crypto');
const { listen, connect } = require('node:quic');

async function main() {
  assert.equal(require('node:tls').ECH_SUPPORTED, true);
  const key = createPrivateKey(fs.readFileSync(path.join(__dirname, 'key.pem')));
  const cert = fs.readFileSync(path.join(__dirname, 'cert.pem'));
  const sessions = [];
  let endpoint, client;
  try {
    endpoint = await listen((session) => {
      sessions.push(session);
      session.closed.catch(() => {});
      session.onstream = (stream) => stream.closed.catch(() => {});
    }, {
      sni: { '*': { keys: [key], certs: [cert] } },
      onheaders(headers) {
        assert.equal(headers[':method'], 'GET');
        this.sendHeaders({ ':status': '200', 'content-type': 'text/plain' });
        this.writer.writeSync(Buffer.from('native-h3'));
        this.writer.endSync();
      },
    });
    client = await connect(endpoint.address, {
      servername: 'localhost', ca: cert, verifyPeer: 'strict',
      keepAlive: 0, enableEarlyData: false,
    });
    client.closed.catch(() => {});
    assert.equal((await client.opened).protocol, 'h3');
    let resolveHeaders;
    const received = new Promise((resolve) => { resolveHeaders = resolve; });
    const stream = await client.createBidirectionalStream({
      headers: { ':method': 'GET', ':scheme': 'https', ':authority': 'localhost', ':path': '/' },
      onheaders(headers) { resolveHeaders(headers); },
    });
    assert.equal((await received)[':status'], 200);
    const chunks = [];
    for await (const batch of stream) {
      for (const chunk of Array.isArray(batch) ? batch : [batch]) chunks.push(Buffer.from(chunk));
    }
    assert.equal(Buffer.concat(chunks).toString(), 'native-h3');
    console.log('NODEJS_MOBILE_QUIC_H3_OK');
  } finally {
    const clientEndpoint = client?.endpoint;
    client?.destroy();
    await clientEndpoint?.close();
    for (const session of sessions) session.destroy();
    await endpoint?.close();
  }
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
