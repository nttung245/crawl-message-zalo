function emitAndExit(payload, code = 0) {
  const data = JSON.stringify(payload) + "\n";
  if (process.stdout.write(data)) {
    process.exit(code);
  } else {
    process.stdout.once('drain', () => process.exit(code));
  }
}
emitAndExit({ok: true}, 0);
