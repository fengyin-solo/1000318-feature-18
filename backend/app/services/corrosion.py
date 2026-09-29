"""防腐检测评级整改规则：关联管段、固化一次判定并跟踪整改证据。"""
from __future__ import annotations

from collections import Counter
from typing import Any

from app.store import store

MODULE = "corrosion"
PIPE_MODULE = "pipe_section"
REQUIRED_FIELDS = ["记录编号", "检测管段", "防腐层类型", "破损点数量"]
STATUS_ORDER = ["待检测", "已检测", "待整改", "整改中", "待复核", "已关闭"]
STATUS_ALIASES = {
    "已检测": "已检测",
    "待修复": "待整改",
    "已修复": "已关闭",
}
ACTION_RULES = {
    "开始检测": "已检测",
    "标记破损": "待整改",
    "提交评级": None,
    "提交整改": "整改中",
    "提交证据": "待复核",
    "人工关闭": "已关闭",
}
# 向后兼容旧页面动作名。
ACTION_ALIASES = {
    "确认修复": "提交证据",
}
DEACTIVATED_PIPE_STATUSES = {"停用", "废弃", "封存", "退役"}
JUDGMENT_PREFIX = "FPR"
DAMAGE_BOUNDARIES = {5, 15, 30}


class CorrosionService:
    def __init__(self) -> None:
        self._seed_ratings_ready = False

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        self._ensure_seed_ratings()
        rows = [self._decorate_row(row) for row in store.rows(MODULE)]
        if keyword:
            rows = [
                row for row in rows
                if keyword in str(row.get("记录编号", ""))
                or keyword in str(row.get("检测管段", ""))
            ]
        if status:
            expected = STATUS_ALIASES.get(status, status)
            rows = [row for row in rows if row.get("status") == expected]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        self._ensure_seed_ratings()
        entry = store.find(MODULE, entry_id)
        return self._decorate_row(entry) if entry else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        try:
            damage_count = int(values.get("破损点数量"))
            if damage_count < 0:
                raise ValueError
        except (TypeError, ValueError):
            return None, ["破损点数量需为不小于 0 的整数"]

        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in REQUIRED_FIELDS:
            entry[field] = damage_count if field == "破损点数量" else values.get(field)
        for field in ["管地电位", "检测日期", "检测人员"]:
            if values.get(field):
                entry[field] = values.get(field)
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        entry["记录状态"] = entry["status"]
        entry["_runtime_created"] = True
        rows.append(entry)
        return self._decorate_row(entry), []

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str, bool]:
        self._ensure_seed_ratings()
        values = values or {}
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"防腐记录 {entry_id} 不存在或已归档", False
        action = ACTION_ALIASES.get(action, action)
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于防腐检测可执行范围", False

        if action == "开始检测":
            return self._move(entry, action, "待检测", "已检测")
        if action == "标记破损":
            return self._move(entry, action, "已检测", "待整改", abnormal=True)
        if action == "提交评级":
            return self._submit_rating(entry, values)
        if action == "提交整改":
            return self._move(entry, action, "待整改", "整改中", abnormal=True)
        if action == "提交证据":
            return self._submit_evidence(entry, values)
        if action == "人工关闭":
            return self._manual_close(entry, values)
        return None, f"动作「{action}」暂不可执行", False

    def rating_overview(self) -> dict[str, Any]:
        """评级总览：所有统计与明细均读取同一次判定对象。"""
        self._ensure_seed_ratings()
        judgments = [self._decorate_row(row) for row in store.rows(MODULE)]
        status_counts = Counter(str(row.get("status")) for row in judgments)
        level_counts = Counter(str(row.get("防腐等级") or "未评级") for row in judgments)
        cards = [
            {"label": "防腐记录", "value": len(judgments)},
            {"label": "待整改", "value": status_counts.get("待整改", 0)},
            {"label": "整改中", "value": status_counts.get("整改中", 0)},
            {"label": "待复核", "value": status_counts.get("待复核", 0)},
            {"label": "已关闭", "value": status_counts.get("已关闭", 0)},
            {"label": "禁止自动关闭", "value": sum(1 for row in judgments if row.get("禁止自动关闭"))},
            {"label": "III/IV级", "value": level_counts.get("III级", 0) + level_counts.get("IV级", 0)},
        ]
        return {
            "cards": cards,
            "items": [self._judgment_brief(self._decorate_row(row)) for row in store.rows(MODULE)],
        }

    def detection_detail(self, entry_id: int) -> dict[str, Any] | None:
        entry = self.get_entry(entry_id)
        if entry is None:
            return None
        pipe = self._find_pipe(str(entry.get("检测管段") or ""))
        judgment = self._display_judgment(entry)
        return {
            "id": entry.get("id"),
            "判定编号": judgment["判定编号"],
            "防腐记录": {
                "id": entry.get("id"),
                "记录编号": entry.get("记录编号"),
                "检测日期": entry.get("检测日期"),
                "检测人员": entry.get("检测人员"),
                "管地电位": entry.get("管地电位"),
                "破损点数量": entry.get("破损点数量"),
            },
            "检测管段": self._pipe_brief(pipe),
            "防腐层类型": entry.get("防腐层类型"),
            "防腐等级": judgment["防腐等级"],
            "评级依据": judgment["评级依据"],
            "风险标记": judgment["风险标记"],
            "禁止自动关闭": judgment["禁止自动关闭"],
            "自动关闭拦截原因": judgment["自动关闭拦截原因"],
            "判定时间": judgment["判定时间"],
        }

    def rectification_progress(self, entry_id: int) -> dict[str, Any] | None:
        entry = self.get_entry(entry_id)
        if entry is None:
            return None
        judgment = self._display_judgment(entry)
        steps = self._progress_steps(entry, judgment)
        current_step = next((step for step in reversed(steps) if step["完成"]), steps[0])
        return {
            "id": entry.get("id"),
            "判定编号": judgment["判定编号"],
            "记录编号": entry.get("记录编号"),
            "检测管段": entry.get("检测管段"),
            "防腐等级": judgment["防腐等级"],
            "状态": entry.get("status"),
            "进度百分比": current_step["进度"],
            "当前节点": current_step["节点"],
            "禁止自动关闭": judgment["禁止自动关闭"],
            "拦截原因": judgment["自动关闭拦截原因"],
            "整改证据编号": entry.get("整改证据编号"),
            "证据复用": judgment.get("证据复用", False),
            "证据复用说明": judgment.get("证据复用说明", ""),
            "判定时间": judgment.get("判定时间", ""),
            "steps": steps,
        }

    def _submit_rating(self, entry: dict[str, Any], values: dict[str, Any]) -> tuple[dict[str, Any], str, bool]:
        if entry.get("判定编号"):
            decorated = self._decorate_row(entry)
            return decorated, f"已生成同一次判定 {decorated['判定编号']}，不得重复评级", False
        if entry.get("status") not in {"已检测", "待整改", "整改中", "待复核"}:
            return self._decorate_row(entry), "完成检测后才能提交评级", False
        pipe = self._find_pipe(str(entry.get("检测管段") or ""))
        if pipe is None:
            return self._decorate_row(entry), f"检测管段 {entry.get('检测管段')} 未在管段档案中建档，不能评级", False

        damage_count = self._damage_count(entry)
        if damage_count is None:
            return self._decorate_row(entry), "破损点数量需为不小于 0 的整数", False
        boundary = damage_count in DAMAGE_BOUNDARIES
        stopped = str(pipe.get("管段状态") or pipe.get("status") or "") in DEACTIVATED_PIPE_STATUSES
        manual_basis = str(values.get("评级依据") or "").strip()
        if (boundary or stopped) and not manual_basis:
            reasons = []
            if boundary:
                reasons.append("破损点数量处于评级交界")
            if stopped:
                reasons.append("检测管段已停用")
            return self._decorate_row(entry), f"{'、'.join(reasons)}，评级必须填写人工判定依据", False
        if manual_basis:
            entry["人工评级依据"] = manual_basis

        judgment = self._create_judgment(entry, pipe, damage_count, boundary, stopped)
        level = str(judgment["防腐等级"])
        if entry.get("status") == "已检测" and (level in {"III级", "IV级"} or judgment["禁止自动关闭"]):
            entry["status"] = "待整改"
        entry["记录状态"] = entry.get("status")
        entry["abnormal"] = level in {"III级", "IV级"} or bool(judgment["风险标记"])
        entry["pending"] = entry.get("status") != "已关闭"
        if judgment["禁止自动关闭"]:
            return self._decorate_row(entry), f"评级已生成：{judgment['判定编号']}；{judgment['自动关闭拦截原因']}", True
        if level in {"I级", "II级"} and not judgment["风险标记"]:
            self._close_entry(entry, judgment, "自动关闭", "低风险且无交界、停用或证据复用限制")
            return self._decorate_row(entry), f"评级已生成并自动关闭：{judgment['判定编号']}", True
        return self._decorate_row(entry), f"评级已生成：{judgment['判定编号']}", True

    def _submit_evidence(self, entry: dict[str, Any], values: dict[str, Any]) -> tuple[dict[str, Any], str, bool]:
        judgment = self._judgment(entry)
        if not entry.get("判定编号"):
            return self._decorate_row(entry), "请先提交防腐评级，再上传整改证据", False
        evidence_no = str(values.get("整改证据编号") or entry.get("整改证据编号") or "").strip()
        if not evidence_no:
            return self._decorate_row(entry), "整改证据编号必填，禁止无证据关闭", False
        owner = self._find_evidence_owner(evidence_no, int(entry["id"]))
        if owner is not None:
            reuse_basis = str(values.get("证据复用依据") or "").strip()
            if not reuse_basis:
                return self._decorate_row(entry), (
                    f"整改证据 {evidence_no} 已被记录 {owner.get('记录编号')} 使用，"
                    "重复使用时必须填写复用依据，且本次整改禁止自动关闭"
                ), False
            entry["证据复用依据"] = reuse_basis
            entry["证据复用"] = True
            entry["证据复用说明"] = (
                f"证据 {evidence_no} 已被 {owner.get('记录编号')} 使用；复用依据：{reuse_basis}"
            )
            existing_flags = list(entry.get("风险标记") or [])
            entry["风险标记"] = list(dict.fromkeys([*existing_flags, "整改证据重复使用"]))
            existing_basis = str(entry.get("评级依据") or "")
            if entry["证据复用说明"] not in existing_basis:
                entry["评级依据"] = f"{existing_basis}；{entry['证据复用说明']}"
            judgment = self._judgment(entry)

        entry["整改证据编号"] = evidence_no
        entry["status"] = "待复核"
        entry["记录状态"] = entry["status"]
        entry["pending"] = True
        entry["abnormal"] = True
        if judgment["禁止自动关闭"]:
            return self._decorate_row(entry), f"证据已提交：{evidence_no}；{judgment['自动关闭拦截原因']}，只能人工复核关闭", True
        self._close_entry(entry, judgment, "自动关闭", "证据有效且不存在交界、停用或复用限制")
        return self._decorate_row(entry), f"整改证据已提交并自动关闭：{evidence_no}", True

    def _manual_close(self, entry: dict[str, Any], values: dict[str, Any]) -> tuple[dict[str, Any], str, bool]:
        if not entry.get("判定编号"):
            return self._decorate_row(entry), "尚未生成评级判定，不能人工关闭", False
        close_basis = str(values.get("关闭依据") or "").strip()
        judgment = self._judgment(entry)
        if judgment["禁止自动关闭"] and not close_basis:
            return self._decorate_row(entry), "该判定禁止自动关闭；人工关闭必须填写复核依据", False
        if not close_basis:
            close_basis = "复核资料完整，准予关闭"
        self._close_entry(entry, judgment, "人工关闭", close_basis)
        return self._decorate_row(entry), f"已人工关闭判定 {judgment['判定编号']}", True

    def _move(
        self,
        entry: dict[str, Any],
        action: str,
        expected_status: str,
        target_status: str,
        *,
        abnormal: bool = False,
    ) -> tuple[dict[str, Any], str, bool]:
        if entry.get("status") != expected_status:
            return self._decorate_row(entry), f"当前状态为「{entry.get('status')}」，不能执行{action}", False
        entry["status"] = target_status
        entry["记录状态"] = target_status
        entry["pending"] = target_status != "已关闭"
        entry["abnormal"] = abnormal
        return self._decorate_row(entry), f"防腐记录已{action}", True

    def _close_entry(
        self,
        entry: dict[str, Any],
        judgment: dict[str, Any],
        close_type: str,
        close_basis: str,
    ) -> None:
        entry["status"] = "已关闭"
        entry["记录状态"] = "已关闭"
        entry["pending"] = False
        entry["abnormal"] = False
        judgment["关闭方式"] = close_type
        judgment["关闭依据"] = close_basis
        judgment["关闭时间"] = str(entry.get("检测日期") or "")
        entry["关闭方式"] = close_type
        entry["关闭依据"] = close_basis
        entry["关闭时间"] = judgment["关闭时间"]

    def _can_close_automatically(self, judgment: dict[str, Any]) -> bool:
        self._refresh_close_lock(judgment)
        return not bool(judgment["禁止自动关闭"])

    def _create_judgment(
        self,
        entry: dict[str, Any],
        pipe: dict[str, Any],
        damage_count: int,
        boundary: bool,
        stopped: bool,
    ) -> dict[str, Any]:
        level, threshold_basis = self._grade(damage_count)
        flags: list[str] = []
        if boundary:
            flags.append("点数处于评级交界")
        if stopped:
            flags.append("管段已停用")
        basis_parts = [
            threshold_basis,
            f"实际破损点数量 {damage_count} 处",
            f"防腐层类型：{entry.get('防腐层类型')}",
        ]
        manual_basis = str(entry.get("人工评级依据") or "").strip()
        if manual_basis:
            basis_parts.append(f"人工依据：{manual_basis}")
        elif str(pipe.get("管段状态") or "") in DEACTIVATED_PIPE_STATUSES:
            basis_parts.append("停用管段不自动关闭，需复核停用范围与后续处置要求")

        judgment = {
            "判定编号": f"{JUDGMENT_PREFIX}-{int(entry['id']):04d}",
            "防腐等级": level,
            "评级依据": "；".join(basis_parts),
            "风险标记": flags,
            "判定时间": f"{entry.get('检测日期') or ''} 10:00",
            "证据复用": False,
            "证据复用说明": "",
        }
        judgment["禁止自动关闭"] = bool(flags)
        judgment["自动关闭拦截原因"] = "、".join(flags) if flags else ""
        entry.update(judgment)
        return judgment

    def _grade(self, damage_count: int) -> tuple[str, str]:
        if damage_count < 5:
            return "I级", "破损点 0-4 处评定为 I级"
        if damage_count < 15:
            return "II级", "破损点 5-14 处评定为 II级（交界点按较高风险处理）"
        if damage_count < 30:
            return "III级", "破损点 15-29 处评定为 III级（交界点按较高风险处理）"
        return "IV级", "破损点 30 处及以上评定为 IV级（交界点按较高风险处理）"

    def _decorate_row(self, raw_row: dict[str, Any]) -> dict[str, Any]:
        row = dict(raw_row)
        row["status"] = STATUS_ALIASES.get(str(row.get("status")), str(row.get("status") or "待检测"))
        if not row.get("记录状态") or row.get("记录状态") in STATUS_ALIASES:
            row["记录状态"] = row["status"]
        pipe = self._find_pipe(str(row.get("检测管段") or ""))
        damage_count = self._damage_count(row)
        if pipe:
            row["管段状态"] = pipe.get("管段状态") or pipe.get("status")
            row["管线类型"] = pipe.get("管线类型")
            row["所在道路"] = pipe.get("所在道路")
        else:
            row.setdefault("管段状态", "未建档")
        judgment = self._display_judgment(row)
        if row.get("判定编号"):
            row["判定编号"] = judgment["判定编号"]
            row["防腐等级"] = judgment["防腐等级"]
            row["评级依据"] = judgment["评级依据"]
            row["风险标记"] = judgment["风险标记"]
            row["禁止自动关闭"] = judgment["禁止自动关闭"]
            row["自动关闭拦截原因"] = judgment["自动关闭拦截原因"]
        if damage_count is not None:
            row["破损点数量"] = damage_count
        if not row.get("判定编号"):
            row["判定编号"] = judgment["判定编号"]
            row["防腐等级"] = judgment["防腐等级"]
            row["评级依据"] = judgment["评级依据"]
            row["风险标记"] = []
            row["禁止自动关闭"] = False
            row["自动关闭拦截原因"] = ""
        row.pop("_runtime_created", None)
        return row

    def _display_judgment(self, entry: dict[str, Any]) -> dict[str, Any]:
        if not entry.get("判定编号"):
            return {
                "判定编号": "未判定",
                "防腐等级": "未评级",
                "评级依据": "完成检测并提交评级后固化判定依据",
                "风险标记": [],
                "判定时间": "",
                "证据复用": False,
                "证据复用说明": "",
                "禁止自动关闭": False,
                "自动关闭拦截原因": "",
                "关闭方式": "",
                "关闭依据": "",
            }
        return self._judgment(entry)

    def _judgment(self, entry: dict[str, Any]) -> dict[str, Any]:
        damage_count = self._damage_count(entry)
        if damage_count is None:
            level, basis = "未评级", "破损点数量缺失，尚未评级"
        else:
            level, basis = self._grade(damage_count)
        flags = list(entry.get("风险标记") or [])
        pipe = self._find_pipe(str(entry.get("检测管段") or ""))
        stopped = bool(pipe and str(pipe.get("管段状态") or pipe.get("status") or "") in DEACTIVATED_PIPE_STATUSES)
        boundary = damage_count in DAMAGE_BOUNDARIES if damage_count is not None else False
        if boundary and "点数处于评级交界" not in flags:
            flags.append("点数处于评级交界")
        if stopped and "管段已停用" not in flags:
            flags.append("管段已停用")
        if entry.get("证据复用") and "整改证据重复使用" not in flags:
            flags.append("整改证据重复使用")

        basis = str(entry.get("评级依据") or basis)
        manual_basis = str(entry.get("人工评级依据") or "").strip()
        if manual_basis and f"人工依据：{manual_basis}" not in basis:
            basis = f"{basis}；人工依据：{manual_basis}"
        judgment = {
            "判定编号": entry.get("判定编号") or f"{JUDGMENT_PREFIX}-{int(entry.get('id', 0)):04d}",
            "防腐等级": entry.get("防腐等级") or level,
            "评级依据": basis,
            "风险标记": flags,
            "判定时间": entry.get("判定时间") or f"{entry.get('检测日期') or ''} 10:00",
            "证据复用": bool(entry.get("证据复用")),
            "证据复用说明": entry.get("证据复用说明") or "",
            "关闭方式": entry.get("关闭方式") or "",
            "关闭依据": entry.get("关闭依据") or "",
        }
        self._refresh_close_lock(judgment)
        return judgment

    def _refresh_close_lock(self, judgment: dict[str, Any]) -> None:
        reasons = list(judgment.get("风险标记") or [])
        if judgment.get("证据复用") and "整改证据重复使用" not in reasons:
            reasons.append("整改证据重复使用")
        judgment["禁止自动关闭"] = bool(reasons)
        judgment["自动关闭拦截原因"] = "、".join(reasons)

    def _progress_steps(self, entry: dict[str, Any], judgment: dict[str, Any]) -> list[dict[str, Any]]:
        status = str(entry.get("status"))
        level = str(judgment["防腐等级"])
        ordered = ["待检测", "已检测", "待整改", "整改中", "待复核", "已关闭"]
        index = ordered.index(status) if status in ordered else 0
        if level in {"I级", "II级"} and status == "已关闭":
            step_nodes = [
                ("检测完成", 100, True, "检测与评级完成，无整改要求"),
                ("评级判定", 100, True, judgment["判定编号"]),
                ("无需整改", 100, True, "低风险自动关闭或人工关闭"),
                ("证据核验", 100, True, judgment.get("关闭依据") or "无需整改证据"),
                ("关闭归档", 100, True, judgment.get("关闭方式") or "已关闭"),
            ]
            return [{"节点": n, "进度": p, "完成": d, "说明": s} for n, p, d, s in step_nodes]

        definitions = [
            ("检测完成", 15, index >= 1, "防腐检测数据已采集"),
            ("评级判定", 30, index >= 2 or bool(entry.get("判定编号")), judgment["判定编号"]),
            ("整改实施", 55, index >= 3, "按评级依据处理破损点"),
            ("证据核验", 80, index >= 4, str(entry.get("整改证据编号") or "等待提交整改证据")),
            ("关闭归档", 100, index >= 5, judgment.get("关闭依据") or judgment["自动关闭拦截原因"] or "等待复核关闭"),
        ]
        return [{"节点": n, "进度": p, "完成": d, "说明": s} for n, p, d, s in definitions]

    def _judgment_brief(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row.get("id"),
            "判定编号": row.get("判定编号"),
            "记录编号": row.get("记录编号"),
            "检测管段": row.get("检测管段"),
            "管段状态": row.get("管段状态"),
            "防腐层类型": row.get("防腐层类型"),
            "破损点数量": row.get("破损点数量"),
            "防腐等级": row.get("防腐等级"),
            "状态": row.get("status"),
            "风险标记": row.get("风险标记"),
            "禁止自动关闭": row.get("禁止自动关闭"),
            "自动关闭拦截原因": row.get("自动关闭拦截原因"),
        }

    def _pipe_brief(self, pipe: dict[str, Any] | None) -> dict[str, Any]:
        if pipe is None:
            return {"管段编号": "未建档", "管段状态": "未建档"}
        return {
            "管段编号": pipe.get("管段编号"),
            "管线类型": pipe.get("管线类型"),
            "材质规格": pipe.get("材质规格"),
            "所在道路": pipe.get("所在道路"),
            "管段状态": pipe.get("管段状态") or pipe.get("status"),
        }

    def _find_pipe(self, pipe_no: str) -> dict[str, Any] | None:
        for pipe in store.rows(PIPE_MODULE):
            if str(pipe.get("管段编号") or "") == pipe_no:
                return pipe
        return None

    def _find_evidence_owner(self, evidence_no: str, current_id: int) -> dict[str, Any] | None:
        for row in store.rows(MODULE):
            if int(row.get("id", 0)) != current_id and str(row.get("整改证据编号") or "") == evidence_no:
                return row
        return None

    def _damage_count(self, row: dict[str, Any]) -> int | None:
        try:
            value = int(row.get("破损点数量"))  # type: ignore[arg-type]
            return value if value >= 0 else None
        except (TypeError, ValueError):
            return None

    def _ensure_seed_ratings(self) -> None:
        """为已完成检测的示例数据固化判定；运行时新建记录仍走动作接口。"""
        if self._seed_ratings_ready:
            return
        self._seed_ratings_ready = True
        evidence_counts = Counter(
            str(row.get("整改证据编号") or "").strip()
            for row in store.rows(MODULE)
            if str(row.get("整改证据编号") or "").strip()
        )
        for row in store.rows(MODULE):
            if row.get("判定编号") or not row.get("检测日期") or row.get("_runtime_created"):
                continue
            pipe = self._find_pipe(str(row.get("检测管段") or ""))
            damage_count = self._damage_count(row)
            if pipe is None or damage_count is None:
                continue
            boundary = damage_count in DAMAGE_BOUNDARIES
            stopped = str(pipe.get("管段状态") or pipe.get("status") or "") in DEACTIVATED_PIPE_STATUSES
            judgment = self._create_judgment(row, pipe, damage_count, boundary, stopped)
            evidence_no = str(row.get("整改证据编号") or "").strip()
            if evidence_no and evidence_counts[evidence_no] > 1:
                judgment["证据复用"] = True
                judgment["证据复用说明"] = f"示例证据 {evidence_no} 被多条整改记录复用"
                judgment["风险标记"].append("整改证据重复使用")
                self._refresh_close_lock(judgment)
                judgment["评级依据"] = f"{judgment['评级依据']}；{judgment['证据复用说明']}"
                row.update(judgment)
            row["status"] = STATUS_ALIASES.get(str(row.get("status")), str(row.get("status")))
            if row["status"] == "已检测" and (
                judgment["防腐等级"] in {"III级", "IV级"} or judgment["禁止自动关闭"]
            ):
                row["status"] = "待整改"
            row["记录状态"] = row["status"]
            row["abnormal"] = row["status"] != "已关闭"
            row["pending"] = row["status"] != "已关闭"
