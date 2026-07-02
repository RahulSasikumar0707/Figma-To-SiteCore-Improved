const useColor = process.stdout.isTTY && !process.env.NO_COLOR;

const paint = (code) => (s) => (useColor ? `\x1b[${code}m${s}\x1b[0m` : s);
export const c = {
  gray: paint('90'),
  green: paint('32'),
  yellow: paint('33'),
  red: paint('31'),
  cyan: paint('36'),
  bold: paint('1'),
};

function stamp() {
  return c.gray(new Date().toISOString().slice(11, 19));
}

export const log = {
  step(msg) { console.log(`${stamp()} ${c.cyan('▶')} ${c.bold(msg)}`); },
  info(msg) { console.log(`${stamp()}   ${msg}`); },
  ok(msg) { console.log(`${stamp()} ${c.green('✔')} ${msg}`); },
  warn(msg) { console.warn(`${stamp()} ${c.yellow('⚠')} ${msg}`); },
  error(msg) { console.error(`${stamp()} ${c.red('✖')} ${msg}`); },
};
