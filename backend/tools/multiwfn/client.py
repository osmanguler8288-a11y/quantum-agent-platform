"""Remote descriptor API. A submission is deliberately never retried."""
from contextlib import ExitStack

import requests

from config.settings import settings


class DescriptorServiceError(Exception):
    def __init__(self, message, status_code=502, uncertain=False):
        super().__init__(message)
        self.status_code = status_code
        self.uncertain = uncertain


class DescriptorClient:
    def _request(self, method, path, **kwargs):
        key = settings.EQV2_API_KEY
        if not key:
            raise DescriptorServiceError('未配置 EQV2_API_KEY，无法连接描述符服务', 503)
        try:
            response = requests.request(
                method, settings.EQV2_API_BASE_URL.rstrip('/') + path,
                headers={'Authorization': 'Bearer ' + key}, timeout=(15, 180), **kwargs,
            )
        except requests.RequestException:
            raise DescriptorServiceError(
                '提交连接中断，无法确认服务端是否已创建任务；原文件已保留，请勿直接重复提交'
                if method == 'POST' else '描述符服务暂时无法连接，请稍后刷新任务',
                uncertain=method == 'POST',
            ) from None
        if not response.ok:
            try:
                detail = response.json().get('detail', '')
            except ValueError:
                detail = ''
            detail = str(detail).replace(key, '[REDACTED]')[:400]
            status = response.status_code
            message = {
                401: '描述符服务鉴权失败，请检查服务器 API Key',
                413: '描述符服务拒绝了过大的文件',
                429: '描述符任务队列已满，请稍后再提交',
                503: '描述符服务忙或触发限流，请稍后重试',
            }.get(status, '描述符服务请求失败')
            if method == 'POST' and status >= 500:
                message = f'描述符服务返回 {status}，无法确认是否已创建任务；原文件已保留，请联系管理员核对，勿重复提交'
            response.close()
            # A 5xx after POST may occur after job creation; don't offer blind resubmission.
            raise DescriptorServiceError(
                message + (f'：{detail}' if detail and status != 401 else ''),
                status_code=status if status in (404, 413, 422, 429, 503) else 502,
                uncertain=method == 'POST' and status >= 500,
            )
        return response

    def submit(self, sources, ti_index, o_indices, methods):
        with ExitStack() as stack:
            files = {kind: (name, stack.enter_context(path.open('rb')), 'application/octet-stream')
                     for kind, (name, path) in sources.items()}
            with self._request('POST', '/v1/descriptors', files=files, data={
                'ti_index': str(ti_index), 'o_indices': o_indices, 'methods': methods,
            }) as response:
                try:
                    payload = response.json()
                    from uuid import UUID
                    UUID(payload['job_id'])
                    return payload
                except (ValueError, KeyError, TypeError):
                    raise DescriptorServiceError('提交响应不完整，无法确认任务编号；原文件已保留，请勿重复提交', uncertain=True) from None

    def status(self, remote_id):
        with self._request('GET', f'/v1/descriptors/jobs/{remote_id}') as response:
            try:
                return response.json()
            except ValueError:
                raise DescriptorServiceError('描述符服务返回了无效状态，请稍后刷新') from None

    def download(self, remote_id, filename):
        return self._request('GET', f'/v1/descriptors/jobs/{remote_id}/files/{filename}', stream=True)
