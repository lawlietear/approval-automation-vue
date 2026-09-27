"""Read current-session departments without executing any page workflow callback."""
import math
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError

PATH = '/amcs/approval/common/getPartjobOrgList.json'
PAGE_SIZE = 10
MAX_ITEMS = 500


def read_departments(frame):
    original_url = frame.url
    parsed = urlsplit(original_url)
    if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password:
        raise ValueError('部门页面来源无效')
    endpoint = f'{parsed.scheme}://{parsed.netloc}{PATH}'

    def fetch(page):
        if frame.url != original_url:
            raise ValueError('读取期间页面已切换，请重新读取')
        response = None
        try:
            # BrowserContext.request shares login cookies, not page ajax hooks/callbacks.
            response = frame.page.context.request.post(
                endpoint, form={'pageNo': str(page), 'pageSize': str(PAGE_SIZE)},
                headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
                timeout=8000, max_redirects=0)
            if response.status != 200:
                raise ValueError(f'部门查询失败（HTTP {response.status}），请检查浏览器登录状态')
            if 'application/json' not in response.headers.get('content-type', '').lower():
                raise ValueError('部门接口未返回JSON，可能登录已失效；未读取缓存')
            if len(response.body()) > 1_000_000:
                raise ValueError('部门响应过大，已停止读取')
            try:
                data = response.json()
            except ValueError:
                raise ValueError('部门响应格式无效') from None
        except PlaywrightError:
            raise ValueError('部门查询连接失败或超时，请检查登录和网络后重试') from None
        finally:
            if response is not None:
                response.dispose()
        if frame.url != original_url:
            raise ValueError('读取期间页面已切换，请重新读取')
        if not isinstance(data, dict) or data.get('redirectUrl') or data.get('errorInfo') or data.get('errorinfo'):
            raise ValueError('部门接口返回异常或登录跳转；未执行跳转')
        total = data.get('total')
        if isinstance(total, str) and total.isascii() and total.isdigit():
            total = int(total)
        if type(total) is not int or not 0 < total <= MAX_ITEMS or not isinstance(data.get('rows'), list):
            raise ValueError('部门总数或列表无效、为空或超出读取上限')
        if 'returncode' in data and str(data['returncode']) == '0':
            raise ValueError('部门接口报告查询失败')
        items = []
        for row in data['rows']:
            if not isinstance(row, dict) or any(not isinstance(row.get(key), str) or not row[key].strip()
                                                for key in ('orgid', 'orgname')):
                raise ValueError('部门编号或名称缺失，未覆盖已保存选项')
            items.append({'id': row['orgid'].strip(), 'name': row['orgname'].strip()})
        expected = min(PAGE_SIZE, total - (page - 1) * PAGE_SIZE)
        if len(items) != expected:
            raise ValueError('部门分页条数不一致，未覆盖已保存选项')
        return total, items

    total, first = fetch(1)
    items = list(first)
    pages = math.ceil(total / PAGE_SIZE)
    for page in range(2, pages + 1):
        current_total, rows = fetch(page)
        if current_total != total:
            raise ValueError('部门总数在读取期间发生变化，请重新读取')
        items.extend(rows)
    if len({row['id'] for row in items}) != total:
        raise ValueError('部门编号重复或分页没有前进，请重新读取')
    if pages > 1 and fetch(1) != (total, first):
        raise ValueError('部门首页在读取期间发生变化，请重新读取')
    return {'items': items, 'complete': True, 'pages': str(pages), 'method': 'live_query'}
