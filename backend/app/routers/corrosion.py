"""防腐检测接口：评级判定总览、检测详情与整改进度共用同一判定编号。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.corrosion import CorrosionService

router = APIRouter(prefix="/api/corrosion", tags=["防腐检测"])

service = CorrosionService()

LIST_FIELDS = ["记录编号", "检测管段", "防腐层类型", "破损点数量", "管地电位", "检测日期", "检测人员", "记录状态"]
STATUSES = ["待检测", "已检测", "待整改", "整改中", "待复核", "已关闭"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按记录编号或检测管段检索"),
    status: str | None = Query(default=None, description="待检测、已检测、待整改、整改中、待复核、已关闭"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按记录编号、检测管段与状态过滤防腐检测列表。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/rating/overview")
def rating_overview() -> dict[str, Any]:
    """评级总览：统计卡片和明细行都从同一次评级判定读取。"""
    return service.rating_overview()


@router.get("/{entry_id}/detection")
def detection_detail(entry_id: int) -> dict[str, Any]:
    """检测详情：展示防腐记录、管段档案、防腐层、破损点数与评级依据。"""
    detail = service.detection_detail(entry_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"防腐记录 {entry_id} 不存在或已归档")
    return detail


@router.get("/{entry_id}/progress")
def rectification_progress(entry_id: int) -> dict[str, Any]:
    """整改进度：返回与评级总览、检测详情相同的判定编号和拦截原因。"""
    progress = service.rectification_progress(entry_id)
    if progress is None:
        raise HTTPException(status_code=404, detail=f"防腐记录 {entry_id} 不存在或已归档")
    return progress


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出防腐检测清单：返回当前全量数据及评级判定字段。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "corrosion", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条防腐记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"防腐记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条防腐记录，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段或字段不合法：{'、'.join(missing)}")
    return ActionResult(ok=True, message="防腐记录已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """执行检测、评级、整改、证据提交和人工关闭；规则拦截由服务层统一处理。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message, ok = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=ok, message=message, entry=entry)
