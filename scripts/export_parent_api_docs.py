"""Regenerate the expanded parent contract and its self-contained OpenAPI fragment."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.main import app


def main():
    spec = app.openapi()
    paths = {path: operations for path, operations in spec['paths'].items() if path.startswith('/api/v1/parent')}
    models = spec['components']['schemas']
    selected = {}

    def collect(value):
        if isinstance(value, dict):
            ref = value.get('$ref', '')
            if ref.startswith('#/components/schemas/'):
                name = ref.rsplit('/', 1)[1]
                if name not in selected:
                    selected[name] = models[name]
                    collect(models[name])
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)
    collect(paths)

    def typename(schema):
        if '$ref' in schema:
            return schema['$ref'].rsplit('/', 1)[1]
        if 'anyOf' in schema:
            return ' / '.join(typename(item) for item in schema['anyOf'])
        if schema.get('type') == 'array':
            return 'array[' + typename(schema.get('items', {})) + ']'
        if 'enum' in schema:
            return 'enum ' + json.dumps(schema['enum'], ensure_ascii=False)
        return schema.get('type', 'object')

    def constraints(schema):
        return '; '.join(f'{key}={json.dumps(schema[key], ensure_ascii=False)}' for key in
            ('default', 'const', 'minimum', 'maximum', 'minLength', 'maxLength', 'minItems', 'maxItems', 'pattern', 'format') if key in schema) or '—'

    samples = {'child_id': 202, 'target_id': 303, 'parent_id': 101, 'message_id': 501,
        'userId': 303, 'applicationId': 301, 'code': 'a' * 43, 'confirmed': True,
        'days': 30, 'displayName': '家人', 'birthYear': 1996, 'city': '南京', 'job': '工程师',
        'content': '你好，想认真了解彼此', 'note': '希望认真了解', 'clientMessageId': 'send-20260906-1',
        'clientCommandId': 'command-20260906-1', 'reasonId': 'other', 'detail': '说明具体情况',
        'name': '家人', 'id': 101, 'parentId': 101, 'childId': 202,
        'expiresAt': '2026-10-06T00:00:00.000Z', 'authorizationExpiresAt': '2026-10-06T00:00:00.000Z',
        'consentVersion': 'parent-consent@1', 'time': 1788652800000,
        'page': 1, 'pageSize': 20, 'total': 0, 'remainingApplications': 3,
        'scopes': ['完善资料', '查看推荐', '私密喜欢', '处理申请', '同意后文字聊天']}

    def example(schema, name='', response=False, depth=0):
        if depth > 6:
            return None
        if '$ref' in schema:
            return example(models[schema['$ref'].rsplit('/', 1)[1]], name, response, depth + 1)
        if name == 'id' and schema.get('type') == 'string':
            return 'parent:101'
        if name in samples:
            return samples[name]
        if schema.get('examples'):
            return schema['examples'][0]
        if 'const' in schema:
            return schema['const']
        if 'default' in schema:
            return schema['default']
        if 'enum' in schema:
            return schema['enum'][0]
        if 'anyOf' in schema:
            choices = schema['anyOf']
            if response and any(item.get('type') == 'null' for item in choices):
                return None
            return example(next(item for item in choices if item.get('type') != 'null'), name, response, depth + 1)
        kind = schema.get('type')
        if kind == 'object' or 'properties' in schema:
            return {key: example(value, key, response, depth + 1) for key, value in schema.get('properties', {}).items()
                    if response or key in schema.get('required', []) or 'default' in value}
        if kind == 'array':
            return [] if not schema.get('minItems') else [example(schema.get('items', {}), '', response, depth + 1)]
        if kind == 'boolean': return False
        if kind in ('integer', 'number'): return schema.get('minimum', 0)
        return '示例'

    lines = ['# 父母端逐字段契约（自动生成）', '',
        '由 `python scripts/export_parent_api_docs.py` 从实际 OpenAPI 生成。业务权限、状态与迁移见 [父母端接口](parent.md)。', '',
        '所有请求使用 `Authorization: Bearer <access_token>`；有 JSON 请求体时使用 `Content-Type: application/json`。成功响应也是 JSON，直接返回业务对象。', '',
        '请求模型的“必填”指客户端输入；响应模型的字段均按 response_model 返回，nullable 字段可为 null。默认空字符串表示未公开或未填写；空数组表示当前没有记录。所有嵌套类型均在下方展开。', '']
    for path, operations in paths.items():
        for method, op in operations.items():
            if method not in {'get', 'post', 'put', 'patch', 'delete'}: continue
            lines.extend([f'## {method.upper()} {path}', '', op.get('summary', ''), '',
                '| 参数 | 位置 | JSON 类型 | 必填 | 默认与约束 | 含义 |', '| --- | --- | --- | --- | --- | --- |'])
            url = path
            for param in op.get('parameters', []):
                schema = param['schema']
                lines.append(f"| `{param['name']}` | {param['in']} | {typename(schema)} | {'是' if param.get('required') else '否'} | {constraints(schema)} | {param.get('description') or schema.get('description') or schema.get('title', param['name'])} |")
                value = samples.get(param['name'], example(schema, param['name']))
                if param['in'] == 'path': url = url.replace('{' + param['name'] + '}', str(value))
                elif param.get('required') or param['name'] in {'page', 'pageSize', 'cursor'}:
                    url += ('&' if '?' in url else '?') + param['name'] + '=' + str(value)
            body = op.get('requestBody', {}).get('content', {}).get('application/json', {}).get('schema')
            lines.extend(['', '```http', method.upper() + ' ' + url, 'Authorization: Bearer <access_token>'])
            if body:
                lines.extend(['Content-Type: application/json', '', json.dumps(example(body), ensure_ascii=False, indent=2)])
            lines.extend(['```', ''])
            lines.append('请求体：`' + typename(body) + '`，字段约束见下方对应模型。' if body else '无请求体。')
            for status, response in op.get('responses', {}).items():
                if not status.startswith('2'): continue
                schema = response.get('content', {}).get('application/json', {}).get('schema', {})
                lines.extend(['', f'成功状态 `{status}`；返回 `{typename(schema)}`。结构示例（空列表为合法空态）：', '', '```json',
                    json.dumps(example(schema, response=True), ensure_ascii=False, indent=2), '```', ''])
    for name, schema in sorted(selected.items()):
        lines.extend(['## ' + name, '', '| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |', '| --- | --- | --- | --- | --- |'])
        for key, value in schema.get('properties', {}).items():
            lines.append(f"| `{key}` | {typename(value)} | {'是' if key in schema.get('required', []) else '否'} | {constraints(value)} | {value.get('description') or value.get('title', key)} |")
        lines.append('')
    target = ROOT / 'docs/api'
    (target / 'parent-contract.generated.md').write_text('\n'.join(lines), encoding='utf-8', newline='\n')
    fragment = {'openapi': spec['openapi'], 'info': {'title': 'Parent API', 'version': '2026-09-06'},
        'paths': paths, 'components': {'schemas': selected, 'securitySchemes': spec['components'].get('securitySchemes', {})}}
    (target / 'parent.openapi.json').write_text(json.dumps(fragment, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(f'Exported {len(paths)} parent paths and {len(selected)} explicit models')


if __name__ == '__main__':
    main()
