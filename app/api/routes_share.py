"""对话片段公开分享 —— 只读 GET,**无需鉴权**。

对应路由 `/api/share/{token}`,被前端 `/s/:token` 公开页消费。token 不可猜,
访问一次 view_count + 1;不存在的 token 返回 404。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.schemas.models import SharedSnapshot

router = APIRouter()


@router.get("/{token}")
async def get_share(token: str) -> dict:
    snap = await SharedSnapshot.filter(token=token).first()
    if not snap:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分享内容不存在或已过期")
    # 浏览计数(原子操作走更新):不阻塞返回,且失败可吞
    try:
        snap.view_count = (snap.view_count or 0) + 1
        await snap.save(update_fields=["view_count"])
    except Exception:
        pass
    return snap.to_public()
