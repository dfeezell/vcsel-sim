// Print an HTML file to PDF with headless Chromium: node render_pdf.js in.html out.pdf
const { chromium } = require('playwright');
const path = require('path');
(async () => {
  const [src, out] = process.argv.slice(2);
  const b = await chromium.launch();
  const p = await b.newPage();
  await p.goto('file://' + path.resolve(src), { waitUntil: 'load' });
  await p.pdf({
    path: out, format: 'Letter', printBackground: true, preferCSSPageSize: true, displayHeaderFooter: true,
    headerTemplate: '<div></div>',
    footerTemplate: '<div style="width:100%;font:8px Arial,sans-serif;color:#777;padding:0 0.85in;display:flex;justify-content:space-between"><span>VCSEL Simulator user manual (draft)</span><span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>',
  });
  await b.close();
})();
