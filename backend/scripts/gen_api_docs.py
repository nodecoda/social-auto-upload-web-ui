#!/usr/bin/env python3
"""从 Flask app 路由表生成 docs/api-reference.md。

用法（backend 目录下）:
    .venv/bin/python scripts/gen_api_docs.py > ../docs/api-reference.md

文档是「机器生成的权威快照」：路由变更后重跑本脚本即可刷新。
无 docstring 的路由会在表格中标注，并在文末列出待补清单。
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
logging.disable(logging.CRITICAL)

import app as appmod

SKIP_RULES = {'/static/<path:filename>'}

# 前端 api 层对照（blueprint 前缀 → frontend/src/api 文件）
FRONTEND_API_MAP = {
    'account': 'account.ts / user.ts',
    'ext_api': 'draft.ts / v2.ts / frame.ts / changelog.ts',
    'materials': 'materials.ts / upload.ts',
    'upload': 'upload.ts',
    'feedback': 'feedback.ts',
    'publish': 'draft.ts / v2.ts',
    'image_publish': 'imagePublish.ts',
    'douyin_image': 'douyinImage.ts',
    'kuaishou_image': 'kuaishouImage.ts',
    'taobao_guanghe': 'taobaoGuanghe.ts',
    'jd_picker': 'jd.ts',
    'frames': 'frame.ts',
    'channels': 'channels.ts',
    'alipay': 'alipay.ts',
    'xiaohongshu': 'xiaohongshu.ts',
    'toutiao': 'toutiao.ts',
    'vivo': 'vivo.ts',
    'bilibili': 'bilibili.ts',
    'weibo': 'weibo.ts',
    'weixin_gzh': 'weixin_gzh.ts',
}


def _doc_first_line(view) -> str:
    doc = (view.__doc__ or '').strip().split('\n')[0].strip() if view else ''
    return doc


def main():
    rules = sorted(appmod.app.url_map.iter_rules(), key=lambda r: (r.rule, sorted(r.methods or [])))
    rows = []
    no_doc = []
    for r in rules:
        if r.rule in SKIP_RULES:
            continue
        methods = ','.join(sorted(m for m in (r.methods or []) if m not in {'HEAD', 'OPTIONS'}))
        view = appmod.app.view_functions.get(r.endpoint)
        doc = _doc_first_line(view)
        ep_prefix = r.endpoint.split('.')[0]
        fe = FRONTEND_API_MAP.get(ep_prefix, '')
        if not doc:
            no_doc.append((methods, r.rule, r.endpoint))
        rows.append((methods or 'GET', r.rule, r.endpoint, doc, fe))

    out = []
    out.append('# API 参考（自动生成）')
    out.append('')
    out.append('> 由 `backend/scripts/gen_api_docs.py` 从 Flask 路由表生成，路由变更后重跑刷新。')
    out.append(f'> 共 {len(rows)} 条路由（不含 static）。')
    out.append('')
    out.append('## 路由总表')
    out.append('')
    out.append('| 方法 | 路径 | endpoint | 说明 | 前端 api 层 |')
    out.append('| --- | --- | --- | --- | --- |')
    for methods, rule, endpoint, doc, fe in rows:
        doc_cell = doc or '*(无 docstring)*'
        fe_cell = fe or ''
        out.append(f'| {methods} | `{rule}` | `{endpoint}` | {doc_cell} | {fe_cell} |')
    out.append('')
    out.append('## 按域分组')
    out.append('')
    # 按 endpoint 前缀分组（不含 static 类）
    groups = {}
    for methods, rule, endpoint, doc, fe in rows:
        if endpoint in {'index', 'custom_static', 'favicon', 'vite_svg', 'serve_changelog', 'health_check'}:
            g = 'app(装配层)'
        else:
            g = endpoint.split('.')[0]
        groups.setdefault(g, []).append((methods, rule, endpoint, doc, fe))
    for g in sorted(groups):
        out.append(f'### {g}')
        out.append('')
        out.append('| 方法 | 路径 | 说明 | 前端 api 层 |')
        out.append('| --- | --- | --- | --- |')
        for methods, rule, _endpoint, doc, fe in sorted(groups[g], key=lambda x: x[1]):
            doc_cell = doc or '*(无 docstring)*'
            out.append(f'| {methods} | `{rule}` | {doc_cell} | {fe} |')
        out.append('')
    out.append('## 待补 docstring 清单')
    out.append('')
    out.append(f'共 {len(no_doc)} 条路由无 docstring（文档可读性缺口）：')
    out.append('')
    for methods, rule, endpoint in sorted(no_doc, key=lambda x: x[1]):
        out.append(f'- {methods} `{rule}`（`{endpoint}`）')
    out.append('')
    print('\n'.join(out))


if __name__ == '__main__':
    main()
