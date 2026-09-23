// Run manually on the device. Saves only local Keychain configuration; no request.
const form = new Alert();
form.title = 'Personal OS capture setup';
form.message = 'Enter the activated capture endpoint and device token. Nothing is sent during setup.';
form.addTextField('https://worker.account.workers.dev/capture');
form.addSecureTextField('Device capture token');
form.addAction('Save on this device');
form.addCancelAction('Cancel');
const choice = await form.presentAlert();
if (choice === 0) {
  const endpoint = form.textFieldValue(0).trim();
  const token = form.textFieldValue(1).trim();
  if (/^https:\/\/[a-z0-9-]+\.[a-z0-9-]+\.workers\.dev\/capture$/.test(endpoint) && token) {
    Keychain.set('personal-os.capture.config', JSON.stringify({ endpoint, token }));
    Script.setShortcutOutput({ status: 'configured' });
  } else {
    Script.setShortcutOutput({ status: 'invalid_configuration' });
  }
} else {
  Script.setShortcutOutput({ status: 'cancelled' });
}
Script.complete();
