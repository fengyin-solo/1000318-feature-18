"""防腐检测接口：维护防腐记录、评级判定和整改跟踪。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.corrosion import CorrosionService

router = APIRouter(prefix="/api/corrosion", tags=["防腐检测"])

service = CorrosionService()

LIST_FIELDS = ["记录编号", "检测管段", "防腐层类型", "破损点数量", "管地电位", "检测日期", "检测人员", "记录状态"]
STATUSES = ["待检测", "已检测", "待修复", "已修复"]
PROGRESSES = ["待评级", "待整改", "整改中", "已关闭"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按记录编号、检测管段或防腐层类型检索"),
    status: str | None = Query(default=None, description="待检测、已检测、待修复、已修复"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """检测详情列表：防腐记录字段与同一次评级判定一并返回。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/ratings/overview")
def rating_overview() -> dict[str, Any]:
    """评级总览：评级数量、拦截量和每条同一判定快照。"""
    return service.rating_overview()


@router.get("/rectifications")
def list_rectifications(
    keyword: str | None = Query(default=None, description="按判定编号、防腐记录、管段或防腐层检索"),
    progress: str | None = Query(default=None, description="待评级、待整改、整改中、已关闭"),
) -> dict[str, Any]:
    """整改进度：读取评级总览和检测详情共用的同一次判定。"""
    items = service.list_tracks(keyword=keyword, progress=progress)
    return {"items": items, "total": len(items)}


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出防腐检测清单：返回当前全量数据及评级跟踪信息。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "corrosion", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict[str, Any]:
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
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="防腐记录已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """执行检测、破损评级或确认修复；自动关闭被拦截时仍返回可读依据。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.values)
    ok = entry is not None and (action != "确认修复" or entry.get("status") == STATUSES[-1])
    return ActionResult(ok=ok, message=message, entry=entry)


@router.post("/{entry_id}/rectification/evidence", response_model=ActionResult)
def submit_evidence(entry_id: int, payload: EntryPayload) -> ActionResult:
    """提交整改证据；证据重复时保留证据但标记禁止自动关闭。"""
    entry, message, ok = service.submit_evidence(entry_id, payload.values)
    return ActionResult(ok=ok, message=message, entry=entry)


@router.post("/{entry_id}/rating/basis", response_model=ActionResult)
def save_rating_basis(entry_id: int, payload: EntryPayload) -> ActionResult:
    """补充边界点数或停用管段等场景所需的人工评级依据。"""
    entry, message, ok = service.save_basis(entry_id, payload.values)
    return ActionResult(ok=ok, message=message, entry=entry)


@router.post("/{entry_id}/rectification/close", response_model=ActionResult)
def close_rectification(entry_id: int, payload: EntryPayload) -> ActionResult:
    """人工核验关闭；自动关闭被禁止时仍可由核验说明承担责任。"""
    entry, message, ok = service.close_rectification(entry_id, payload.values)
    return ActionResult(ok=ok, message=message, entry=entry)
