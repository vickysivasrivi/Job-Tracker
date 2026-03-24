/**
 * pdf_builder.js — Zero-dependency PDF generator
 * Produces a clean A4 professional resume PDF using raw PDF 1.4 syntax.
 * Called by server.js: buildResumePDF(data) → Buffer
 */

'use strict';

const FONT_NORMAL  = 'Helvetica';
const FONT_BOLD    = 'Helvetica-Bold';
const PAGE_W       = 595.28;  // A4 points
const PAGE_H       = 841.89;
const ML = 50, MR = 50, MT = 45, MB = 45;
const CW = PAGE_W - ML - MR;

class PDFBuilder {
  constructor() {
    this.objects  = [];   // [ { id, lines[] } ]
    this.pages    = [];   // page object ids
    this.content  = [];   // content stream lines per page
    this.pageObjs = [];   // page dict ids
    this.xrefs    = [];
    this._id      = 0;
    this.curPage  = null;
    this.y        = 0;
  }

  _obj(lines) {
    const id = ++this._id;
    this.objects.push({ id, lines });
    return id;
  }

  _esc(s) {
    return String(s)
      .replace(/\\/g, '\\\\')
      .replace(/\(/g, '\\(')
      .replace(/\)/g, '\\)')
      .replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\xff]/g, ' ');
  }

  // ── Page management ────────────────────────────────────────────────────────
  newPage() {
    if (this.curPage !== null) this._finalizePage();
    this.curPage = [];
    this.y = PAGE_H - MT;
  }

  _finalizePage() {
    const stream = this.curPage.join('\n');
    const len    = Buffer.byteLength(stream, 'utf8');
    const streamId = this._obj([
      '<<',
      `/Length ${len}`,
      '>>',
      'stream',
      stream,
      'endstream'
    ]);
    const pageId = this._obj([
      '<<',
      '/Type /Page',
      '/Parent 2 0 R',
      `/MediaBox [0 0 ${PAGE_W} ${PAGE_H}]`,
      '/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >>',
      `/Contents ${streamId} 0 R`,
      '>>'
    ]);
    this.pageObjs.push(pageId);
    this.curPage = null;
  }

  // ── Drawing helpers ────────────────────────────────────────────────────────
  _push(...lines) { this.curPage.push(...lines); }

  _text(x, y, txt, font, size, color) {
    const c = color || '0 0 0';
    this._push(
      `BT`,
      `/${font} ${size} Tf`,
      `${c} rg`,
      `${x} ${y} Td`,
      `(${this._esc(txt)}) Tj`,
      `ET`
    );
  }

  _line(x1, y1, x2, y2, width, r, g, b) {
    this._push(
      `${r||0} ${g||0} ${b||0} RG`,
      `${width||0.5} w`,
      `${x1} ${y1} m`,
      `${x2} ${y2} l`,
      `S`
    );
  }

  // ── Word wrap ──────────────────────────────────────────────────────────────
  _wrapText(txt, maxWidth, font, size) {
    // Approximate: Helvetica avg char width ≈ 0.52 * size
    const avgW = (font === FONT_BOLD ? 0.58 : 0.52) * size;
    const maxChars = Math.floor(maxWidth / avgW);
    const words = String(txt || '').split(' ');
    const lines = [];
    let cur = '';
    for (const w of words) {
      const test = cur ? cur + ' ' + w : w;
      if (test.length <= maxChars) { cur = test; }
      else {
        if (cur) lines.push(cur);
        // if single word is too long, hard-break
        if (w.length > maxChars) {
          let rem = w;
          while (rem.length > maxChars) { lines.push(rem.slice(0, maxChars)); rem = rem.slice(maxChars); }
          cur = rem;
        } else { cur = w; }
      }
    }
    if (cur) lines.push(cur);
    return lines;
  }

  // ── High-level layout ──────────────────────────────────────────────────────
  _checkNewPage(needed) {
    if (this.y - needed < MB) { this.newPage(); }
  }

  drawName(name) {
    this._checkNewPage(32);
    this._text(ML, this.y, name, FONT_BOLD, 22);
    this.y -= 26;
  }

  drawContact(contact) {
    if (!contact) return;
    this._checkNewPage(16);
    this._text(ML, this.y, contact, FONT_NORMAL, 9, '0.35 0.35 0.35');
    this.y -= 14;
  }

  drawHRule(thick, r, g, b) {
    this._checkNewPage(8);
    this._line(ML, this.y, PAGE_W - MR, this.y, thick || 0.8, r||0, g||0, b||0);
    this.y -= 8;
  }

  drawSectionTitle(title) {
    this._checkNewPage(22);
    this.y -= 4;
    this._text(ML, this.y, String(title).toUpperCase(), FONT_BOLD, 9, '0.1 0.1 0.1');
    this.y -= 4;
    this.drawHRule(0.4, 0.75, 0.75, 0.75);
  }

  drawParagraph(txt, indent) {
    if (!txt) return;
    const x   = ML + (indent || 0);
    const maxW = CW - (indent || 0);
    const lines = this._wrapText(txt, maxW, FONT_NORMAL, 10);
    for (const ln of lines) {
      this._checkNewPage(14);
      this._text(x, this.y, ln, FONT_NORMAL, 10);
      this.y -= 13;
    }
    this.y -= 2;
  }

  drawJobHeader(role, company, period) {
    this._checkNewPage(18);
    this.y -= 2;
    // Role in bold
    const roleW = (role.length * 0.58 * 11);
    this._text(ML, this.y, role, FONT_BOLD, 11);
    // Company in grey after role
    if (company) {
      const cx = ML + Math.min(roleW + 6, CW * 0.55);
      this._text(cx, this.y, '— ' + company, FONT_NORMAL, 10, '0.35 0.35 0.35');
    }
    // Period right-aligned
    if (period) {
      const pw = period.length * 0.52 * 9;
      this._text(PAGE_W - MR - pw, this.y, period, FONT_NORMAL, 9, '0.45 0.45 0.45');
    }
    this.y -= 14;
  }

  drawBullet(txt) {
    if (!txt) return;
    const indent = 14;
    const maxW   = CW - indent - 10;
    const lines  = this._wrapText(txt, maxW, FONT_NORMAL, 10);
    for (let i = 0; i < lines.length; i++) {
      this._checkNewPage(13);
      if (i === 0) this._text(ML + indent - 8, this.y, '\u2022', FONT_NORMAL, 10);
      this._text(ML + indent, this.y, lines[i], FONT_NORMAL, 10);
      this.y -= 12;
    }
  }

  drawSkillLine(txt) {
    if (!txt) return;
    const lines = this._wrapText(txt, CW, FONT_NORMAL, 10);
    for (const ln of lines) {
      this._checkNewPage(13);
      this._text(ML, this.y, ln, FONT_NORMAL, 10);
      this.y -= 12;
    }
    this.y -= 2;
  }

  // ── Build complete PDF buffer ──────────────────────────────────────────────
  buildFromData(data) {
    // Reserve object ids: 1=catalog, 2=pages, 3=font-normal, 4=font-bold
    this._id = 4;

    this.newPage();

    // Name & contact
    this.drawName(data.name || 'Candidate');
    if (data.contact) this.drawContact(data.contact);
    this.drawHRule(1.2);
    this.y -= 2;

    // Sections
    for (const sec of (data.sections || [])) {
      const title   = sec.title || '';
      const content = sec.content || [];
      this.drawSectionTitle(title);

      for (const item of content) {
        if (typeof item === 'string') {
          // Plain text / skills
          this.drawSkillLine(item);
        } else if (typeof item === 'object') {
          // Job/edu entry
          this.drawJobHeader(item.role || '', item.company || '', item.period || '');
          if (item.description) this.drawParagraph(item.description, 0);
          for (const b of (item.bullets || [])) {
            if (b && b.trim()) this.drawBullet(b);
          }
          this.y -= 4;
        }
      }
      this.y -= 4;
    }

    // Finalize last page
    if (this.curPage !== null) this._finalizePage();

    return this._compile();
  }

  _compile() {
    // Build the fixed objects first: catalog(1), pages(2), fonts(3,4)
    // then all dynamic objects (pages, streams)
    const catalog = { id: 1, lines: ['<<', '/Type /Catalog', '/Pages 2 0 R', '>>'] };
    const pagesDict = {
      id: 2,
      lines: [
        '<<',
        '/Type /Pages',
        `/Kids [${this.pageObjs.map(p => p + ' 0 R').join(' ')}]`,
        `/Count ${this.pageObjs.length}`,
        '>>'
      ]
    };
    const fontNormal = { id: 3, lines: ['<<', '/Type /Font', '/Subtype /Type1', '/BaseFont /Helvetica', '/Encoding /WinAnsiEncoding', '>>'] };
    const fontBold   = { id: 4, lines: ['<<', '/Type /Font', '/Subtype /Type1', '/BaseFont /Helvetica-Bold', '/Encoding /WinAnsiEncoding', '>>'] };

    const allObjs = [catalog, pagesDict, fontNormal, fontBold, ...this.objects];
    // Sort by id
    allObjs.sort((a, b) => a.id - b.id);

    const lines  = ['%PDF-1.4'];
    const offsets = {};

    for (const obj of allObjs) {
      offsets[obj.id] = lines.join('\n').length + 1;
      lines.push(`${obj.id} 0 obj`);
      lines.push(...obj.lines);
      lines.push('endobj');
      lines.push('');
    }

    const xrefOffset = lines.join('\n').length + 1;
    const maxId = Math.max(...allObjs.map(o => o.id));
    lines.push('xref');
    lines.push(`0 ${maxId + 1}`);
    lines.push('0000000000 65535 f ');
    for (let i = 1; i <= maxId; i++) {
      const off = offsets[i];
      lines.push((off !== undefined ? String(off).padStart(10, '0') : '0000000000') + ' 00000 n ');
    }
    lines.push('trailer');
    lines.push('<<');
    lines.push(`/Size ${maxId + 1}`);
    lines.push('/Root 1 0 R');
    lines.push('>>');
    lines.push('startxref');
    lines.push(String(xrefOffset));
    lines.push('%%EOF');

    return Buffer.from(lines.join('\n'), 'utf8');
  }
}

function buildResumePDF(data) {
  const builder = new PDFBuilder();
  return builder.buildFromData(data);
}

module.exports = { buildResumePDF };
