"""防腐检测评级与整改跟踪规则。

评级结果在评级总览、检测详情、整改进度之间共用同一份判定快照；
边界点数、停用管段、重复整改证据均会阻止“确认修复”自动关闭。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "corrosion"
PIPE_MODULE = "pipe_section"
REQUIRED_FIELDS = ["记录编号", "检测管段", "防腐层类型"]
STATUS_ORDER = ["待检测", "已检测", "待修复", "已修复"]
ACTION_RULES = {"开始检测": "已检测", "标记破损": "待修复", "确认修复": "已修复"}
NEGATIVE_ACTIONS = []

RATING_BOUNDARIES = (4, 11, 21)
ACTIVE_PIPE_STATUSES = {"在役", "运行", "正常", "启用"}
DETAIL_FIELDS = ["破损点数量", "管地电位", "检测日期", "检测人员", "记录状态"]


class CorrosionService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [
                row for row in rows
                if keyword in str(row.get("记录编号", ""))
                or keyword in str(row.get("检测管段", ""))
                or keyword in str(row.get("防腐层类型", ""))
            ]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        rows = [self._with_tracking_fields(row) for row in rows]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        return self._with_tracking_fields(entry)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        if _to_int(values.get("破损点数量")) is not None:
            entry["破损点数量"] = _to_int(values.get("破损点数量"))
        for field in DETAIL_FIELDS:
            if field in values and values.get(field) not in (None, ""):
                entry[field] = values.get(field)
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def rating_overview(self) -> dict[str, Any]:
        """返回各评级的汇总，以及三张页面共用的同一批判定快照。"""
        tracks = self._all_tracks()
        levels = ["一级", "二级", "三级", "四级", "未评级"]
        summary: list[dict[str, Any]] = []
        for level in levels:
            level_rows = [item for item in tracks if item["防腐评级"] == level]
            summary.append({
                "评级": level,
                "数量": len(level_rows),
                "待整改": sum(1 for item in level_rows if item["整改进度"] == "待整改"),
                "整改中": sum(1 for item in level_rows if item["整改进度"] == "整改中"),
                "已关闭": sum(1 for item in level_rows if item["整改进度"] == "已关闭"),
                "禁止自动关闭": sum(1 for item in level_rows if item["禁止自动关闭"]),
            })
        return {
            "items": summary,
            "tracks": tracks,
            "total": len(tracks),
            "pendingRectification": sum(1 for item in tracks if item["整改进度"] != "已关闭"),
            "blockedAutoClose": sum(1 for item in tracks if item["禁止自动关闭"]),
            "reusedEvidence": sum(1 for item in tracks if item["整改证据重复使用"]),
        }

    def list_tracks(self, keyword: str | None = None, progress: str | None = None) -> list[dict[str, Any]]:
        tracks = self._all_tracks()
        if keyword:
            tracks = [
                item for item in tracks
                if keyword in str(item["判定编号"])
                or keyword in str(item["记录编号"])
                or keyword in str(item["检测管段"])
                or keyword in str(item["防腐层类型"])
            ]
        if progress:
            tracks = [item for item in tracks if item["整改进度"] == progress]
        return tracks

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        values = values or {}
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"防腐记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于防腐检测可执行范围"

        if action == "开始检测":
            track = self._ensure_track(entry)
            self._sync_entry(entry, track)
            return self.get_entry(entry_id), "防腐记录已开始检测，评级判定已生成"

        if action == "标记破损":
            count = _to_int(entry.get("破损点数量"))
            if count is None:
                return None, "破损点数量缺失或不是整数，无法按评级边界判定并生成整改单"
            track = self._ensure_track(entry)
            track["整改进度"] = "待整改"
            track = self._refresh_track(track, entry)
            self._sync_entry(entry, track)
            return self.get_entry(entry_id), "破损点已纳入评级，整改跟踪单已生成"

        evidence = str(values.get("整改证据") or values.get("evidence") or "").strip()
        basis_note = str(values.get("评级依据说明") or values.get("basisNote") or "").strip()
        if entry.get("status") == STATUS_ORDER[-1]:
            return None, "整改已关闭，不能重复确认修复"
        if not evidence:
            return None, "请提交整改证据后再确认修复"

        track = self._ensure_track(entry)
        if basis_note:
            track["人工评级依据"] = basis_note
        self._register_evidence(track, evidence)
        track = self._refresh_track(track, entry)

        if track["禁止自动关闭"]:
            track["整改进度"] = "整改中"
            self._sync_entry(entry, track)
            reasons = "、".join(track["拦截原因"])
            message = f"整改证据已记录，但同一次判定禁止自动关闭：{reasons}"
            return self.get_entry(entry_id), message

        self._close_track(entry, track)
        return self.get_entry(entry_id), "整改证据有效，防腐记录已自动关闭"

    def submit_evidence(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str, bool]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"防腐记录 {entry_id} 不存在或已归档", False
        evidence = str(values.get("整改证据") or "").strip()
        if not evidence:
            return None, "整改证据编号、照片编号或报告编号不能为空", False
        if entry.get("status") == STATUS_ORDER[0]:
            return None, "检测尚未完成，不能提交整改证据", False
        if entry.get("status") == STATUS_ORDER[-1]:
            return None, "整改已关闭，不能重复提交证据", False

        track = self._ensure_track(entry)
        track["整改证据"] = evidence
        self._register_evidence(track, evidence)
        track["整改进度"] = "整改中"
        track = self._refresh_track(track, entry)
        self._sync_entry(entry, track)
        if track["整改证据重复使用"]:
            return self.get_entry(entry_id), "整改证据与既有判定重复，已标记并禁止自动关闭", False
        return self.get_entry(entry_id), "整改证据已登记", True

    def save_basis(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str, bool]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"防腐记录 {entry_id} 不存在或已归档", False
        basis_note = str(values.get("评级依据说明") or "").strip()
        if not basis_note:
            return None, "评级依据说明不能为空", False
        track = self._ensure_track(entry)
        track["人工评级依据"] = basis_note
        track = self._refresh_track(track, entry)
        self._sync_entry(entry, track)
        return self.get_entry(entry_id), "评级依据已补充，评级总览、检测详情和整改进度使用同一判定", True

    def close_rectification(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str, bool]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"防腐记录 {entry_id} 不存在或已归档", False
        if entry.get("status") == STATUS_ORDER[0]:
            return None, "检测尚未完成，不能关闭整改", False
        if entry.get("status") == STATUS_ORDER[-1]:
            return None, "整改已关闭，不能重复关闭", False
        track = self._ensure_track(entry)
        if not str(track.get("整改证据") or "").strip():
            return None, "缺少整改证据，不能人工关闭", False
        closure_note = str(values.get("核验说明") or "").strip()
        if not closure_note:
            return None, "人工核验关闭必须填写核验说明", False
        track["人工核验说明"] = closure_note
        track = self._refresh_track(track, entry)
        self._close_track(entry, track, manual=True)
        return self.get_entry(entry_id), "整改已人工核验关闭；本次未执行自动关闭，拦截标识随当前判定保留", True

    def _all_tracks(self) -> list[dict[str, Any]]:
        tracks: list[dict[str, Any]] = []
        for entry in store.rows(MODULE):
            if entry.get("status") != STATUS_ORDER[0]:
                tracks.append(self._track_view(self._ensure_track(entry), entry))
        return tracks

    def _ensure_track(self, entry: dict[str, Any]) -> dict[str, Any]:
        """从防腐记录生成或取回判定，保证所有页面看到同一次判定。"""
        table = store.rows("corrosion_tracking")
        entry_id = int(entry.get("id", 0))
        for track in table:
            if int(track.get("防腐记录ID", 0)) == entry_id:
                return track

        count = _to_int(entry.get("破损点数量"))
        track = {
            "id": max((int(item.get("id", 0)) for item in table), default=0) + 1,
            "判定编号": f"R-CORR-{entry_id:04d}",
            "判定版本": 1,
            "防腐记录ID": entry_id,
            "记录编号": entry.get("记录编号", ""),
            "检测管段": entry.get("检测管段", ""),
            "防腐层类型": entry.get("防腐层类型", ""),
            "破损点数量": count,
            "防腐评级": _rating_for_count(count),
            "评级依据": _rating_basis(count),
            "完整评级依据": _rating_basis(count),
            "边界点数": count in RATING_BOUNDARIES if count is not None else False,
            "管段停用": not self._pipe_is_active(entry.get("检测管段")),
            "整改证据": entry.get("整改证据", ""),
            "整改证据重复使用": False,
            "禁止自动关闭": False,
            "拦截原因": [],
            "判定时间": entry.get("检测日期") or date.today().isoformat(),
            "整改进度": _initial_progress(entry),
            "人工评级依据": entry.get("人工评级依据", ""),
            "人工核验说明": "",
        }
        table.append(track)
        return self._refresh_track(track, entry)

    def _refresh_track(self, track: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
        count = _to_int(entry.get("破损点数量"))
        track.update({
            "记录编号": entry.get("记录编号", ""),
            "检测管段": entry.get("检测管段", ""),
            "防腐层类型": entry.get("防腐层类型", ""),
            "破损点数量": count,
            "防腐评级": _rating_for_count(count),
            "边界点数": count in RATING_BOUNDARIES if count is not None else False,
            "管段停用": not self._pipe_is_active(entry.get("检测管段")),
        })
        evidence = str(track.get("整改证据") or "").strip()
        track["整改证据重复使用"] = bool(evidence and self._evidence_used_elsewhere(track, evidence))

        reasons: list[str] = []
        if track["边界点数"]:
            reasons.append(f"破损点数量 {count} 处处于评级交界，须说明取级依据")
        if track["管段停用"]:
            reasons.append("检测管段已停用，不得按在役管段自动关闭")
        if track["整改证据重复使用"]:
            reasons.append(f"整改证据「{evidence}」已被其他判定使用")
        track["拦截原因"] = reasons
        track["禁止自动关闭"] = bool(reasons)
        track["评级依据"] = _rating_basis(
            count,
            stopped=bool(track["管段停用"]),
            reused_evidence=track["整改证据重复使用"],
            evidence=evidence,
        )
        parts = [str(track["评级依据"])]
        if str(track.get("人工评级依据") or "").strip():
            parts.append(f"人工依据：{track['人工评级依据']}")
        if str(track.get("人工核验说明") or "").strip():
            parts.append(f"核验说明：{track['人工核验说明']}")
        track["完整评级依据"] = "；".join(parts)
        return track

    def _track_view(self, track: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
        refreshed = self._refresh_track(dict(track), entry)
        track.clear()
        track.update(refreshed)
        view = dict(track)
        view["记录状态"] = entry.get("status")
        return view

    def _with_tracking_fields(self, entry: dict[str, Any]) -> dict[str, Any]:
        result = dict(entry)
        if entry.get("status") == STATUS_ORDER[0]:
            result.update({
                "判定编号": "—",
                "防腐评级": "未评级",
                "评级依据": "检测完成后生成同一次判定",
                "完整评级依据": "检测完成后生成同一次判定",
                "禁止自动关闭": False,
                "拦截原因": [],
                "整改进度": "待检测",
                "整改证据重复使用": False,
                "管段停用": not self._pipe_is_active(entry.get("检测管段")),
            })
            return result
        track = self._track_view(self._ensure_track(entry), entry)
        result.update({key: value for key, value in track.items() if key != "id"})
        return result

    def _sync_entry(self, entry: dict[str, Any], track: dict[str, Any]) -> None:
        progress = str(track.get("整改进度") or "")
        if progress == "已关闭":
            status = STATUS_ORDER[-1]
        elif progress in {"待整改", "整改中"}:
            status = "待修复"
        else:
            status = "已检测"
        entry["status"] = status
        entry["记录状态"] = status
        entry["pending"] = status != STATUS_ORDER[-1]
        entry["abnormal"] = status == "待修复"
        entry["判定编号"] = track.get("判定编号")
        entry["防腐评级"] = track.get("防腐评级")
        entry["评级依据"] = track.get("评级依据")
        entry["禁止自动关闭"] = track.get("禁止自动关闭", False)
        entry["整改进度"] = track.get("整改进度")
        entry["整改证据"] = track.get("整改证据", "")
        entry["整改证据重复使用"] = track.get("整改证据重复使用", False)
        entry["拦截原因"] = list(track.get("拦截原因", []))

    def _close_track(self, entry: dict[str, Any], track: dict[str, Any], *, manual: bool = False) -> None:
        track["整改进度"] = "已关闭"
        track["关闭方式"] = "人工核验关闭" if manual else "自动关闭"
        track["关闭时间"] = date.today().isoformat()
        self._sync_entry(entry, track)

    def _pipe_is_active(self, pipe_label: Any) -> bool:
        label = str(pipe_label or "").strip()
        pipes = store.rows(PIPE_MODULE)
        if not label:
            return False
        candidates = [
            pipe for pipe in pipes
            if str(pipe.get("管段编号") or "").strip() == label
            or str(pipe.get("status") or "").strip() == label
            or str(pipe.get("管段状态") or "").strip() == label
        ]
        if not candidates:
            candidates = [
                pipe for pipe in pipes
                if any(label in str(value or "") for value in pipe.values())
            ]
        for pipe in candidates:
            status = str(pipe.get("status") or pipe.get("管段状态") or "").strip()
            if status not in ACTIVE_PIPE_STATUSES:
                return False
        return bool(candidates)

    def _register_evidence(self, track: dict[str, Any], evidence: str) -> None:
        usage = store.rows("corrosion_evidence_usage")
        owner_id = int(track.get("防腐记录ID", 0))
        exists = any(
            int(item.get("防腐记录ID", 0)) == owner_id and str(item.get("整改证据")) == evidence
            for item in usage
        )
        track["整改证据"] = evidence
        if not exists:
            usage.append({
                "id": max((int(item.get("id", 0)) for item in usage), default=0) + 1,
                "防腐记录ID": owner_id,
                "判定编号": track.get("判定编号"),
                "整改证据": evidence,
            })

    def _evidence_used_elsewhere(self, track: dict[str, Any], evidence: str) -> bool:
        owner_id = int(track.get("防腐记录ID", 0))
        return any(
            int(item.get("防腐记录ID", 0)) != owner_id and str(item.get("整改证据")) == evidence
            for item in store.rows("corrosion_evidence_usage")
        )


def _initial_progress(entry: dict[str, Any]) -> str:
    status = str(entry.get("status") or "")
    if status == STATUS_ORDER[-1]:
        return "已关闭"
    if status == "待修复":
        return "待整改"
    if _to_int(entry.get("破损点数量")) is None:
        return "待评级"
    return "待整改"


def _to_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    text = str(value or "").strip()
    if not text:
        return None
    try:
        number = int(text)
    except ValueError:
        return None
    return number if number >= 0 else None


def _rating_for_count(count: int | None) -> str:
    if count is None:
        return "未评级"
    if count <= 4:
        return "一级"
    if count <= 11:
        return "二级"
    if count <= 21:
        return "三级"
    return "四级"


def _rating_basis(
    count: int | None,
    *,
    stopped: bool = False,
    reused_evidence: bool = False,
    evidence: str = "",
) -> str:
    if count is None:
        basis = "破损点数量缺失，检测完成后补录并评级"
    elif count in RATING_BOUNDARIES:
        basis = f"破损点 {count} 处处于评级交界；自动规则暂按{_rating_for_count(count)}取级，须人工说明最终依据"
    elif count < 4:
        basis = f"破损点 {count} 处，少于一级/二级交界 4 处，评为一级"
    elif count < 11:
        basis = f"破损点 {count} 处，大于 4 处且小于二级/三级交界 11 处，评为二级"
    elif count < 21:
        basis = f"破损点 {count} 处，大于 11 处且小于三级/四级交界 21 处，评为三级"
    else:
        basis = f"破损点 {count} 处，大于三级/四级交界 21 处，评为四级"
    notes: list[str] = []
    if stopped:
        notes.append("检测管段已停用，评级仅作为停用管段整改依据，禁止自动关闭")
    if reused_evidence:
        notes.append(f"整改证据「{evidence}」重复使用，须补充独立复验证据，禁止自动关闭")
    return "；".join([basis, *notes])
