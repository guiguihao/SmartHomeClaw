// 验证设备列表表格的完整卡片 JSON — 修复版
function parseTableRow(line) {
  const trimmed = line.trim();
  const inner = trimmed.startsWith('|') ? trimmed.slice(1) : trimmed;
  const inner2 = inner.endsWith('|') ? inner.slice(0, -1) : inner;
  return inner2.split('|').map(c => c.trim());
}

function parseMarkdownToCardElements(text) {
  if (!text) return [{ tag: 'div', text: { tag: 'lark_md', content: '无内容' } }];
  const lines = text.split('\n');
  const elements = [];
  let i = 0;
  let tableHeaderLine = null;
  let tableRows = [];
  let inTable = false;
  let listItems = [];
  let listType = null;
  let paragraphLines = [];

  function flushParagraph() {
    if (paragraphLines.length === 0) return;
    elements.push({ tag: 'div', text: { tag: 'lark_md', content: paragraphLines.join('\n') } });
    paragraphLines = [];
  }
  function flushList() {
    if (listItems.length === 0) return;
    elements.push({ tag: 'div', text: { tag: 'lark_md', content: listItems.join('\n') } });
    listItems = []; listType = null;
  }
  function flushTable() {
    if (!tableHeaderLine || tableRows.length === 0) { inTable = false; tableHeaderLine = null; tableRows = []; return; }
    const headers = parseTableRow(tableHeaderLine);
    const colCount = headers.length;
    const columns = [];
    for (let c = 0; c < colCount; c++) {
      const cellLines = [`**${headers[c] || ''}**`];
      for (const row of tableRows) {
        const cells = parseTableRow(row);
        cellLines.push(cells[c] || '–');
      }
      columns.push({
        tag: 'column', width: 'weighted', weight: 1,
        elements: [{ tag: 'div', text: { tag: 'lark_md', content: cellLines.join('\n') } }],
      });
    }
    elements.push({ tag: 'column_set', flex_mode: 'bisect', horizontal_spacing: '8px', columns });
    inTable = false; tableHeaderLine = null; tableRows = [];
  }

  while (i < lines.length) {
    const line = lines[i];
    if (line.trim() === '---') { flushParagraph(); flushList(); flushTable(); elements.push({ tag: 'hr' }); i++; continue; }
    const isTableLine = line.trim().startsWith('|');
    if (isTableLine) {
      flushParagraph(); flushList();
      const trimmed = line.trim();
      const inner = trimmed.startsWith('|') ? trimmed.slice(1) : trimmed;
      const innerClean = inner.endsWith('|') ? inner.slice(0, -1) : inner;
      const cells = innerClean.split('|').map(c => c.trim());
      const isSeparator = cells.length > 0 && cells.every(c => /^[\s\-:]+$/.test(c));
      if (!inTable && !isSeparator) { inTable = true; tableHeaderLine = line; }
      else if (inTable && isSeparator) { }
      else if (inTable && !isSeparator) { tableRows.push(line); }
      i++; continue;
    } else if (inTable) { flushTable(); }
    const headingMatch = line.match(/^#{1,4}\s+(.+)/);
    if (headingMatch) { flushParagraph(); flushList(); flushTable(); elements.push({ tag: 'div', text: { tag: 'lark_md', content: `**${headingMatch[1]}**` } }); i++; continue; }
    const orderedMatch = line.match(/^(\s*)(\d+)[.)]\s+(.+)/);
    if (orderedMatch) { flushParagraph(); if (listType !== 'ordered') flushList(); listType = 'ordered'; listItems.push(orderedMatch[3]); i++; continue; }
    const unorderedMatch = line.match(/^(\s*)[-*+]\s+(.+)/);
    if (unorderedMatch && line.trim() !== '---') { flushParagraph(); if (listType !== 'unordered') flushList(); listType = 'unordered'; listItems.push(`• ${unorderedMatch[2]}`); i++; continue; }
    if (line.trim() === '') { flushList(); if (paragraphLines.length > 0) paragraphLines.push(''); i++; continue; }
    flushList(); flushTable(); paragraphLines.push(line); i++;
  }
  flushParagraph(); flushList(); flushTable();
  if (elements.length === 0) elements.push({ tag: 'div', text: { tag: 'lark_md', content: text } });
  return elements;
}

function buildCardContent(text) {
  const elements = parseMarkdownToCardElements(text);
  let headerTitle = '🏠 SmartHomeClaw';
  let headerTemplate = 'blue';
  let bodyElements = elements;
  if (elements.length > 0) {
    const first = elements[0];
    if (first.tag === 'div' && first.text?.tag === 'lark_md') {
      const boldTitleMatch = first.text.content.match(/^\*\*([^*]+)\*\*$/);
      if (boldTitleMatch) {
        headerTitle = boldTitleMatch[1];
        bodyElements = elements.slice(1);
        const t = headerTitle.toLowerCase();
        if (t.includes('设备') || t.includes('控制')) headerTemplate = 'turquoise';
        else if (t.includes('错误')) headerTemplate = 'red';
        else if (t.includes('成功')) headerTemplate = 'green';
      }
    }
  }
  if (bodyElements.length === 0) { bodyElements = elements; headerTitle = '🏠 SmartHomeClaw'; }
  return JSON.stringify({ config: { wide_screen_mode: true }, header: { title: { tag: 'plain_text', content: headerTitle }, template: headerTemplate }, elements: bodyElements });
}

// ── 测试 ──
const input = `#### 2️⃣ 设备列表（子设备）
| DID | 别名 | 型号 | 所属房间 | 房间所在楼层 | 备注 |
|-----|------|------|----------|--------------|------|
| 1001 | ZigBee转RS485 | RL‑ZTC‑ZB‑UR‑01 | 设备区域（0） | – | 用作 ZigBee‑RS485 桥接 |
| 1003 | 温控器 | RL‑AFD‑COM‑UR‑04 | 餐厅（rid = 15） | -1F | 仅 addr = 1 |
| 1004 | 二合一温控器 | RL‑FHD‑ZB‑LF‑03 | 餐厅（rid = 13） | 1F | addr = C498 |
| 1005 | 二合一温控器 | RL‑FHD‑ZB‑LF‑03 | 次卧`;

const card = JSON.parse(buildCardContent(input));
console.log('Header:', card.header.title.content, card.header.template);
console.log('Element types:', card.elements.map(e => e.tag));

// 检查 column_set
const cs = card.elements.find(e => e.tag === 'column_set');
if (cs) {
  console.log('Table columns:', cs.columns.length);
  console.log('DID column rows:');
  console.log(cs.columns[0].elements[0].text.content);
  console.log('\n备注 column rows:');
  console.log(cs.columns[5].elements[0].text.content);
}

// 检查没有残留 div
const divs = card.elements.filter(e => e.tag === 'div');
if (divs.length > 0) {
  console.log('\n剩余 div 元素:');
  for (const d of divs) {
    console.log(`  → ${d.text.content.substring(0, 50)}`);
  }
}