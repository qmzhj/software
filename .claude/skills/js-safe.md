---
name: js-safe
description: 编辑 JS/HTML 后自动检查花括号平衡，以及解决 onclick 等 HTML 属性中的转义问题
---

## 花括号平衡检查

每次编辑 JS 代码后（尤其是编辑了 `<script>` 内的内容后），运行以下检查：

```bash
python3 -c "
import re, sys
with open('$FILE', 'r') as f:
    content = f.read()
m = re.search(r'<script>(.*?)</script>', content, re.DOTALL)
if not m:
    sys.exit(0)
js = m.group(1)
depth = 0
in_str = False
quote = ''
for ch in js:
    if in_str:
        if ch == '\\\\':
            continue
        if ch == quote:
            in_str = False
    else:
        if ch in ('\"', \"'\"', '\`'):
            in_str = True
            quote = ch
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
if depth != 0:
    print(f'ERROR: 花括号不平衡, depth={depth}')
    sys.exit(1)
else:
    print('OK: 花括号平衡')
"
```

如果检查失败，用以下方式定位问题：

```bash
python3 -c "
import re
with open('$FILE', 'r') as f:
    content = f.read()
m = re.search(r'<script>(.*?)</script>', content, re.DOTALL)
js = m.group(1)
lines = js.split(chr(10))
depth = 0
in_str = False
quote = ''
for li, line in enumerate(lines):
    i = 0
    while i < len(line):
        ch = line[i]
        if in_str:
            if ch == chr(92) and i+1 < len(line):
                i += 2; continue
            if ch == quote:
                in_str = False
        else:
            if ch in (chr(39), chr(34), chr(96)):  # ', \", \`
                in_str = True
                quote = ch
            elif ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth < 0:
                    print(f'多余的 }} 在行 {li+1}: {line.strip()[:80]}')
                    raise SystemExit(1)
        i += 1
print(f'深度: {depth}' + (' (不平衡!)' if depth != 0 else ' (平衡)'))
"
```

## HTML onclick 转义（"转义地狱"解决方案）

### 问题

当在 JS 中构建 HTML 字符串，并将动态内容嵌入 `onclick` 属性时：
```js
return '<div onclick="handler(\'' + content + '\')">...</div>';
```
如果 `content` 包含 `'`、`\`、`\n`、`&` 等字符，HTML 属性值会断裂。

### 方案 A（推荐）：data-* 属性 + 事件委托

不在 onclick 中嵌入数据，而是通过 dataset 传递：

**在字符串模板中：**
```js
return '<div class="clickable" data-payload="' + attrEncode(JSON.stringify(data)) + '">...</div>';
```

**在事件处理中：**
```js
document.addEventListener('click', function(e) {
  const el = e.target.closest('.clickable');
  if (!el) return;
  const data = JSON.parse(el.dataset.payload);
  // 处理 data
});
```

其中 `attrEncode`：
```js
function attrEncode(s) {
  return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}
```

### 方案 B（简单场景少量数据）：专门转义函数

当必须用 onclick 时，用这个转义：

```js
function jsAttr(s) {
  return s.replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/\n/g, '\\n').replace(/</g, '\\u003C');
}
```

使用：
```js
return '<div onclick="handler(\'' + jsAttr(content) + '\')">...</div>';
```

### 方案 C（最好）：不构建 HTML 字符串，用 DOM API

```js
const div = document.createElement('div');
div.className = 'clickable';
div.textContent = '...';
div.addEventListener('click', function() {
  handler(data);  // data 在闭包中，无需转义
});
```

此方案完全避免转义问题，推荐用于新功能。
