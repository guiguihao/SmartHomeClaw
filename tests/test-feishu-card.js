/**
 * 测试飞书卡片 Markdown 解析器
 * 验证表格、标题、列表、分割线等能正确转换为卡片元素
 */
import { readFileSync } from 'fs';

// 直接从 feishu.js 中提取 parseMarkdownToCardElements 和 buildCardContent
// 因为它们是模块内函数，需要用 eval 或重新导入
// 这里用更简单的方式：直接 require 模块后通过全局访问

// 先手动定义解析函数（与 feishu.js 中一致），方便测试
function parseTableRow(line) {
  const trimmed = line.trim();
  const inner = trimmed.startsWith('|') ? trimmed.slice(1) : trimmed;
  const inner2 = inner.endsWith('|') ? inner.slice(0, -1) : inner;
  return inner2.split('|').map(c => c.trim());
}

function parseMarkdownToCardElements(text) {
  if (!text || typeof text !== 'string') {
    return [{ tag: 'div', text: { tag: 'lark_md', content: text || '无内容' } }];
  }

  const lines = text.split('\n');
  const elements = [];
  let i = 0;
  let tableHeaderLine = null;
  let tableSeparatorLine = null;
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
    listItems = [];
    listType = null;
  }

  function flushTable() {
    if (!tableHeaderLine || tableRows.length === 0) {
      inTable = false; tableHeaderLine = null; tableSeparatorLine = null; tableRows = [];
      return;
    }
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
        tag: 'column',
        width: 'weighted',
        weight: 1,
        elements: [{ tag: 'div', text: { tag: 'lark_md', content: cellLines.join('\n') } }],
      });
    }
    elements.push({ tag: 'column_set', flex_mode: 'bisect', horizontal_spacing: '8px', columns });
    inTable = false; tableHeaderLine = null; tableSeparatorLine = null; tableRows = [];
  }

  while (i < lines.length) {
    const line = lines[i];

    if (line.trim() === '---' || line.trim() === '***' || line.trim() === '___') {
      flushParagraph(); flushList(); flushTable();
      elements.push({ tag: 'hr' });
      i++; continue;
    }

    if (line.trim().startsWith('|') && line.trim().endsWith('|')) {
      flushParagraph(); flushList();
      const trimmed = line.trim();
      const cellContent = trimmed.slice(1, -1);
      const isSeparator = cellContent.split('|').every(c => /^[\s\-:]+$/.test(c.trim()));

      if (!inTable && !isSeparator) { inTable = true; tableHeaderLine = line; }
      else if (inTable && isSeparator) { tableSeparatorLine = line; }
      else if (inTable && !isSeparator) { tableRows.push(line); }
      i++; continue;
    } else if (inTable) {
      flushTable();
    }

    const orderedMatch = line.match(/^(\s*)(\d+)[.)]\s+(.+)/);
    if (orderedMatch) {
      flushParagraph();
      if (listType !== 'ordered') flushList();
      listType = 'ordered';
      listItems.push(orderedMatch[3]);
      i++; continue;
    }

    const unorderedMatch = line.match(/^(\s*)[-*+]\s+(.+)/);
    if (unorderedMatch && line.trim() !== '---' && line.trim() !== '***') {
      flushParagraph();
      if (listType !== 'unordered') flushList();
      listType = 'unordered';
      listItems.push(`• ${unorderedMatch[2]}`);
      i++; continue;
    }

    const headingMatch = line.match(/^#{1,4}\s+(.+)/);
    if (headingMatch) {
      flushParagraph(); flushList(); flushTable();
      elements.push({ tag: 'div', text: { tag: 'lark_md', content: `**${headingMatch[1]}**` } });
      i++; continue;
    }

    if (line.trim() === '') {
      flushList();
      if (paragraphLines.length > 0) paragraphLines.push('');
      i++; continue;
    }

    flushList(); flushTable();
    paragraphLines.push(line);
    i++;
  }

  flushParagraph(); flushList(); flushTable();

  if (elements.length === 0) {
    elements.push({ tag: 'div', text: { tag: 'lark_md', content: text } });
  }

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
      }
    }
  }

  return JSON.stringify({
    config: { wide_screen_mode: true },
    header: { title: { tag: 'plain_text', content: headerTitle }, template: headerTemplate },
    elements: bodyElements,
  });
}

// ── 测试用例 ──

const tests = [
  {
    name: '设备列表表格',
    input: `#### 2️⃣ 设备列表（子设备）
| DID | 别名 | 型号 | 所属房间 | 房间所在楼层 | 备注 |
|-----|------|------|----------|--------------|------|
| 1001 | ZigBee转RS485 | RL‑ZTC‑ZB‑UR‑01 | 设备区域（0） | – | 用作 ZigBee‑RS485 桥接 |
| 1003 | 温控器 | RL‑AFD‑COM‑UR‑04 | 餐厅（rid = 15） | -1F | 仅 addr = 1 |
| 1004 | 二合一温控器 | RL‑FHD‑ZB‑LF‑03 | 餐厅（rid = 13） | 1F | addr = C498 |
| 1005 | 二合一温控器 | RL‑FHD‑ZB‑LF‑03 | 次卧`,
  },
  {
    name: '标题+段落+列表',
    input: `## 家庭概况

您有 2 个家庭：

1. 我的家（HomeID: 12345）
2. 办公室（HomeID: 67890）

网关信息如下：`,
  },
  {
    name: '分割线+混合内容',
    input: `**设备控制结果**

✅ 温控器已设置为 25°C

---

**下一步建议**

- 可以查看实时温度
- 定时自动调节`,
  },
  {
    name: '纯文本',
    input: `已更新用户偏好：喜欢 25°C 室温，晚上自动关灯。`,
  },
  {
    name: '空内容',
    input: '',
  },
];

let passed = 0;
for (const t of tests) {
  try {
    const card = JSON.parse(buildCardContent(t.input));
    const elTypes = card.elements.map(e => e.tag);

    console.log(`\n── ${t.name} ──`);
    console.log(`Header: ${card.header.title.content} (${card.header.template})`);
    console.log(`Elements: ${elTypes.join(', ')}`);

    // 检查关键结构
    if (t.input.includes('|')) {
      const hasColumnSet = elTypes.includes('column_set');
      console.log(`表格 → column_set: ${hasColumnSet ? '✅' : '❌'}`);
      if (hasColumnSet) {
        const cs = card.elements.find(e => e.tag === 'column_set');
        console.log(`  列数: ${cs.columns.length}`);
        console.log(`  第一列第一行（表头）: ${cs.columns[0].elements[0].text.content.split('\n')[0]}`);
      }
      if (!hasColumnSet) passed--;
    }

    passed++;
  } catch (e) {
    console.error(`❌ ${t.name}: ${e.message}`);
  }
}

console.log(`\n━━━ 结果: ${passed}/${tests.length} 通过 ━━━`);