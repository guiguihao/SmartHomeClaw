/**
 * 测试飞书卡片 table 组件生成
 */

function parseTableRow(line) {
  const trimmed = line.trim();
  const inner = trimmed.startsWith('|') ? trimmed.slice(1) : trimmed;
  const inner2 = inner.endsWith('|') ? inner.slice(0, -1) : inner;
  return inner2.split('|').map(c => c.trim());
}

function isTableSeparatorLine(line) {
  const trimmed = line.trim();
  if (!trimmed.startsWith('|')) return false;
  const inner = trimmed.slice(1);
  const inner2 = inner.endsWith('|') ? inner.slice(0, -1) : inner;
  const cells = inner2.split('|').map(c => c.trim());
  return cells.length > 0 && cells.every(c => /^[\s\-:]+$/.test(c));
}

function markdownTableToFeishuTable(headerLine, dataLines) {
  const headers = parseTableRow(headerLine);
  const columns = headers.map((h, idx) => ({
    name: `col_${idx}`,
    display_name: h,
    data_type: 'text',
    width: 'auto',
  }));
  const rows = dataLines.map(line => {
    const cells = parseTableRow(line);
    const row = {};
    columns.forEach((col, idx) => {
      row[col.name] = cells[idx] || '–';
    });
    return row;
  });
  return { tag: 'table', page_size: rows.length > 5 ? 5 : rows.length, columns, rows };
}

function parseMarkdownToCardElements(text) {
  if (!text) return [{ tag: 'div', text: { tag: 'lark_md', content: text || '无内容' } }];
  const lines = text.split('\n');
  const elements = [];
  let i = 0;
  let tableHeaderLine = null;
  let tableDataLines = [];
  let inTable = false;
  let paragraphLines = [];

  function flushParagraph() {
    if (paragraphLines.length === 0) return;
    elements.push({ tag: 'div', text: { tag: 'lark_md', content: paragraphLines.join('\n') } });
    paragraphLines = [];
  }
  function flushTable() {
    if (!tableHeaderLine || tableDataLines.length === 0) { inTable = false; tableHeaderLine = null; tableDataLines = []; return; }
    elements.push(markdownTableToFeishuTable(tableHeaderLine, tableDataLines));
    inTable = false; tableHeaderLine = null; tableDataLines = [];
  }

  while (i < lines.length) {
    const line = lines[i];
    if (line.trim().startsWith('|')) {
      flushParagraph();
      if (isTableSeparatorLine(line)) { i++; continue; }
      if (!inTable) { inTable = true; tableHeaderLine = line; }
      else { tableDataLines.push(line); }
      i++; continue;
    } else if (inTable) { flushTable(); }
    paragraphLines.push(line); i++;
  }
  flushParagraph(); flushTable();
  if (elements.length === 0) elements.push({ tag: 'div', text: { tag: 'lark_md', content: text } });
  return elements;
}

function buildCardContent(text) {
  const elements = parseMarkdownToCardElements(text);
  return JSON.stringify({
    config: { wide_screen_mode: true },
    header: { title: { tag: 'plain_text', content: '🏠 SmartHomeClaw' }, template: 'blue' },
    elements,
  });
}

// ── 测试用例 ──

const input1 = `您有 2 个家庭，以下是设备列表：

| DID | 别名 | 型号 | 所属房间 | 楼层 | 备注 |
|-----|------|------|----------|------|------|
| 1001 | ZigBee转RS485 | RL-ZTC-ZB-UR-01 | 设备区域 | – | 桥接 |
| 1003 | 温控器 | RL-AFD-COM-UR-04 | 餐厅 | -1F | addr=1 |
| 1005 | 二合一温控器 | RL-FHD-ZB-LF-03 | 次卧 | 2F | 自动 |

如需控制某个设备，请告诉我！`;

const card1 = JSON.parse(buildCardContent(input1));
console.log('── 测试1: 混合文本+表格 ──');
console.log('Elements:', card1.elements.map(e => e.tag));

const table1 = card1.elements.find(e => e.tag === 'table');
if (table1) {
  console.log('Table columns:', table1.columns.map(c => c.display_name));
  console.log('Table rows:', table1.rows.length);
  console.log('Row 0:', JSON.stringify(table1.rows[0]));
  console.log('Row 2 (次卧, 少列):', JSON.stringify(table1.rows[2]));
} else {
  console.log('❌ No table element found!');
}

const div1 = card1.elements.filter(e => e.tag === 'div');
console.log('Div elements:', div1.length);
if (div1.length > 0) {
  console.log('First div content (前30字):', div1[0].text.content.substring(0, 30));
  console.log('Last div content (前30字):', div1[div1.length-1].text.content.substring(0, 30));
}

// ── 测试2: 纯文本无表格 ──
const input2 = `已将调光面板（DID 1007）的亮度调至 20%。`;
const card2 = JSON.parse(buildCardContent(input2));
console.log('\n── 测试2: 纯文本 ──');
console.log('Elements:', card2.elements.map(e => e.tag));
console.log('Content:', card2.elements[0].text.content);

// ── 测试3: 多表格 ──
const input3 = `家庭列表：

| HomeID | 名称 | 位置 |
|-------|------|------|
| 12345 | 我的家 | 北京 |

设备列表：

| DID | 别名 | 型号 |
|-----|------|------|
| 1001 | 温控器 | RL-01 |`;

const card3 = JSON.parse(buildCardContent(input3));
console.log('\n── 测试3: 多表格 ──');
console.log('Elements:', card3.elements.map(e => e.tag));
const tables3 = card3.elements.filter(e => e.tag === 'table');
console.log('Tables count:', tables3.length);
console.log('Table1 headers:', tables3[0].columns.map(c => c.display_name));
console.log('Table2 headers:', tables3[1].columns.map(c => c.display_name));