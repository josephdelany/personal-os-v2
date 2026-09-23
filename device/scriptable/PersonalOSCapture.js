// Install alongside PersonalOSQueue.js in Scriptable. Recording stays in Shortcuts.
// Run Script: Parameter = metadata dictionary; Files = saved recording.
// Parameter {replay:true} with no Files runs the hourly replay path.
const transport = importModule('PersonalOSQueue');
let output;
try {
  const fm = FileManager.local();
  const q = transport.queue({ fm, root: fm.joinPath(fm.documentsDirectory(), 'PersonalOSCapture'),
    randomUUID: () => UUID.string(), request: url => new Request(url),
    timer: (ms, fn) => Timer.schedule(ms, false, fn) });
  const metadata = args.shortcutParameter;
  let capture_id;
  if (!metadata || metadata.replay !== true) {
    if (args.fileURLs.length !== 1) throw new Error('one_saved_recording_required');
    capture_id = q.save(args.fileURLs[0], metadata);
  }
  const { endpoint = '', token = '' } = Keychain.contains('personal-os.capture.config')
    ? JSON.parse(Keychain.get('personal-os.capture.config')) : {};
  output = capture_id ? await q.submit(capture_id, { endpoint, token })
    : await q.replay({ endpoint, token });
} catch {
  // Source file must already be saved by Shortcuts. No network error dialog/log.
  output = { status: 'unconfirmed', error: 'capture_not_confirmed' };
}
Script.setShortcutOutput(output);
Script.complete();
