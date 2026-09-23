// ADR-0153. Local durable queue; no recording, UI, model, or secret logging.
const UUID7 = /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
function uuid7(at, randomUUID) {
  const ms = Date.parse(at);
  if (!Number.isSafeInteger(ms) || ms < 0 || ms > 281474976710655) throw new Error('capture_time');
  const random = randomUUID.toLowerCase().replace(/-/g, '');
  if (!/^[0-9a-f]{12}4[0-9a-f]{3}[89ab][0-9a-f]{15}$/.test(random)) throw new Error('random_uuid');
  const time = ms.toString(16).padStart(12, '0');
  return `${time.slice(0,8)}-${time.slice(8)}-7${random.slice(13,16)}-${random.slice(16,20)}-${random.slice(20)}`;
}
function queue(platform) {
  const { fm, root } = platform;
  const path = (...parts) => parts.reduce((a,b) => fm.joinPath(a,b), root);
  for (const name of ['media','staging','manifests','pending','acknowledged']) fm.createDirectory(path(name), true);
  function save(source, metadata) {
    if (!metadata || !['food','note','workout'].includes(metadata.kind)
        || !Number.isFinite(metadata.duration_s) || metadata.duration_s <= 0
        || typeof metadata.captured_at !== 'string'
        || !/(?:Z|[+-]\d{2}:\d{2})$/.test(metadata.captured_at)) throw new Error('metadata');
    const cid = uuid7(metadata.captured_at, platform.randomUUID());
    const media = path('media', cid);
    if (fm.fileExists(path('manifests', `${cid}.jsonl`))) throw new Error('identity_collision');
    // copy refuses replacement and preserves the Shortcut-owned source recording.
    fm.copy(source, media);
    const envelope = { capture_id: cid, media_kind: 'voice', content_type: 'audio/mp4',
      metadata: { captured_at: metadata.captured_at, kind: metadata.kind, duration_s: metadata.duration_s } };
    const line = JSON.stringify(envelope) + '\n';
    fm.writeString(path('staging', `${cid}.jsonl`), line);
    // Keep a validated recovery copy; never publish unparseable queue metadata.
    if (fm.readString(path('staging', `${cid}.jsonl`)) !== line) throw new Error('save_unconfirmed');
    fm.copy(path('staging', `${cid}.jsonl`), path('manifests', `${cid}.jsonl`));
    if (fm.readString(path('manifests', `${cid}.jsonl`)) !== line) throw new Error('save_unconfirmed');
    fm.copy(path('manifests', `${cid}.jsonl`), path('pending', `${cid}.jsonl`));
    return cid;
  }
  function readValid(folder, name) {
    try {
      const entry = JSON.parse(fm.readString(path(folder,name)));
      if (entry.capture_id !== name.slice(0,-6) || !UUID7.test(entry.capture_id)
          || entry.media_kind !== 'voice' || entry.content_type !== 'audio/mp4'
          || !['food','note','workout'].includes(entry.metadata.kind)
          || !Number.isFinite(entry.metadata.duration_s) || entry.metadata.duration_s <= 0
          || !Number.isFinite(Date.parse(entry.metadata.captured_at))) return null;
      return JSON.stringify(entry) + '\n';
    } catch { return null; }
  }
  function recover() {
    let recovery_errors = 0;
    const names = [...new Set([...fm.listContents(path('staging')), ...fm.listContents(path('manifests')),
      ...fm.listContents(path('media')).filter(x => UUID7.test(x)).map(x => x + '.jsonl')])];
    for (const name of names) {
      if (!name.endsWith('.jsonl') || !UUID7.test(name.slice(0,-6))) continue;
      try {
        const staged = readValid('staging',name), manifest = readValid('manifests',name);
        if ((!staged && !manifest) || (staged && manifest && staged !== manifest)) {
          recovery_errors++; continue;
        }
        const valid = manifest || staged;
        // Repair torn publications only from a complete, validated saved copy.
        for (const folder of ['manifests','pending']) {
          if (folder === 'pending' && readValid('acknowledged',name) === valid) continue;
          const existing = readValid(folder,name);
          if (existing && existing !== valid) throw new Error('conflicting_identity');
          if (!existing) {
            const temp = path(folder, name + '.' + platform.randomUUID() + '.tmp');
            fm.writeString(temp,valid);
            if (fm.readString(temp) !== valid) throw new Error('repair_unconfirmed');
            fm.move(temp,path(folder,name));
          }
        }
      } catch { recovery_errors++; }
    }
    return recovery_errors;
  }
  async function sendOne(name, config) {
    let timer;
    try {
      if (!/^[0-9a-f-]+\.jsonl$/.test(name) || !UUID7.test(name.slice(0,-6))) return false;
      const line = readValid('pending',name);
      if (!line || line !== readValid('manifests',name)) return false;
      const entry = JSON.parse(line);
      if (entry.capture_id !== name.slice(0,-6) || entry.media_kind !== 'voice'
          || entry.content_type !== 'audio/mp4') return false;
      if (!/^https:\/\/[a-z0-9-]+\.[a-z0-9-]+\.workers\.dev\/capture$/.test(config.endpoint)
          || typeof config.token !== 'string' || !config.token.trim()) return false;
      const request = platform.request(config.endpoint);
      request.method = 'POST';
      request.timeoutInterval = 10; // idle timeout; the timer below is the total wait bound
      request.onRedirect = () => null;
      request.headers = { Authorization: `Bearer ${config.token}`, 'Content-Type': entry.content_type,
        'X-Capture-ID': entry.capture_id, 'X-Media-Kind': 'voice',
        'X-Capture-Metadata': JSON.stringify(entry.metadata) };
      request.body = fm.read(path('media',entry.capture_id));
      const expired = Symbol('deadline');
      const response = await Promise.race([
        request.loadJSON().catch(() => null),
        new Promise(resolve => { timer = platform.timer(10000, () => resolve(expired)); }),
      ]);
      if (response === expired || !response || response.capture_id !== entry.capture_id) return false;
      const status = request.response && request.response.statusCode;
      if (!(status === 202 || (status === 200 && response.status === 'duplicate'))) return false;
      // Retain manifest/media. Remove only the pending queue line, after durable marker.
      const priorAck = readValid('acknowledged',name);
      if (priorAck && priorAck !== line) return false;
      if (!priorAck) {
        const temp = path('acknowledged', name + '.' + platform.randomUUID() + '.tmp');
        fm.writeString(temp,line);
        if (fm.readString(temp) !== line) return false;
        fm.move(temp,path('acknowledged',name));
      }
      if (readValid('acknowledged',name) !== line) return false;
      if (fm.fileExists(path('pending',name))) fm.remove(path('pending',name));
      return true;
    } catch { return false; }
    finally { if (timer) timer.invalidate(); }
  }
  async function replay(config) {
    const recovery_errors = recover();
    const names = fm.listContents(path('pending')).filter(x => x.endsWith('.jsonl')).sort();
    let acknowledged = 0;
    for (const name of names) if (await sendOne(name,config)) acknowledged++;
    return { acknowledged, pending: fm.listContents(path('pending')).filter(x => x.endsWith('.jsonl')).length, recovery_errors };
  }
  async function submit(cid, config) {
    if (!UUID7.test(cid)) throw new Error('capture_identity');
    const acknowledged = await sendOne(`${cid}.jsonl`, config);
    return { capture_id: cid, status: acknowledged ? 'acknowledged' : 'queued' };
  }
  return { save, replay, recover, submit };
}
module.exports = { uuid7, queue };
