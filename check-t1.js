const fs = require('fs');
const s = fs.readFileSync('index.html', 'utf8');
if (!/type="file"[^>]*accept="video\/\*/.test(s)) throw new Error('no video input');
if (!/data-value="20s"/.test(s)) throw new Error('missing 20s length');
if (!/<video[^>]*playsinline/.test(s)) throw new Error('no preview video');
console.log('upload check ok');
