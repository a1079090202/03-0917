"""服务层公共件：业务异常、单号生成。"""
import uuid
from datetime import datetime


class BizError(Exception):
    """业务规则拒绝（效期、停售、FEFO、库存不足等）。路由层统一转 4xx。"""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def gen_no(prefix: str, when: datetime) -> str:
    return f"{prefix}{when:%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"
