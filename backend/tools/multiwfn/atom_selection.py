"""Shared FCHK atom selection for platform preflight and the remote descriptor service."""
import math
import re


def read_atomic_numbers(path):
    with path.open(encoding='utf-8', errors='replace') as source:
        for line in source:
            if line[:43].strip() != 'Atomic numbers':
                continue
            match = re.search(r'N=\s*(\d+)', line[43:])
            if not match or not 1 <= int(match[1]) <= 200:
                raise ValueError('FCHK 原子数应在 1–200 之间')
            count = int(match[1])
            values = []
            for row in source:
                try:
                    values.extend(int(value) for value in row.split())
                except ValueError:
                    raise ValueError('FCHK Atomic numbers 段不完整') from None
                if len(values) >= count:
                    if len(values) != count or any(not 1 <= n <= 118 for n in values):
                        raise ValueError('FCHK 原子序数不合法')
                    return values
            raise ValueError('FCHK Atomic numbers 段不完整')
    raise ValueError('文件中未找到 FCHK Atomic numbers 段，请上传有效的格式化 checkpoint 文件')


def select_titanium(numbers, requested=0):
    if requested:
        if not 1 <= requested <= len(numbers) or numbers[requested - 1] != 22:
            raise ValueError(f'第 {requested} 个原子不是 Ti，请填写正确的 Ti 编号或留空自动识别')
        return requested
    candidates = [i + 1 for i, number in enumerate(numbers) if number == 22]
    if len(candidates) > 1:
        raise ValueError('检测到多个 Ti 原子，请在分析选项中指定编号：' + ', '.join(map(str, candidates)))
    return candidates[0] if candidates else None


def validate_oxygens(numbers, titanium, requested):
    if requested is None:
        return None
    if titanium is None or len(requested) != 2 or len(set(requested)) != 2 or any(
        not 1 <= index <= len(numbers) or numbers[index - 1] != 8 for index in requested
    ):
        raise ValueError('请提供该结构中两个不同 O 原子的编号；没有 Ti 时不能指定 Ti–O 分析')
    return list(requested)


def select_oxygens(numbers, coordinates, titanium, requested=None):
    explicit = validate_oxygens(numbers, titanium, requested)
    if explicit is not None or titanium is None:
        return explicit
    if len(coordinates) != len(numbers) * 3 or not all(math.isfinite(v) for v in coordinates):
        raise ValueError('FCHK 原子坐标不完整或存在非有限数值')
    origin = coordinates[(titanium - 1) * 3:titanium * 3]
    candidates = [i + 1 for i, number in enumerate(numbers) if number == 8]
    if len(candidates) < 2:
        return None
    return sorted(candidates, key=lambda index: math.dist(
        origin, coordinates[(index - 1) * 3:index * 3],
    ))[:2]
