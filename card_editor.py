from __future__ import annotations

import ctypes
import os
import shutil
import sys
import tkinter as tk
from dataclasses import dataclass, replace
from pathlib import Path
from tkinter import messagebox, ttk

from cards import (
    ACTION_PARAMETER_DEFAULTS,
    ACTION_SPECS,
    ACTION_STATS,
    ACTION_TRIGGERS,
    CATEGORY_SPECS,
    OPERATOR_SPECS,
    RARITIES,
    STACKING_SPECS,
    STAT_SPECS,
    STAT_TARGETS,
    TARGET_BOSS,
    TARGET_ELITE,
    TARGET_GATE,
    TARGET_NORMAL,
    TARGET_PLAYER,
    TRIGGER_SPECS,
    Card,
    CardEffect,
    EffectTargets,
    ParameterValue,
    action_defaults,
    default_cards_path,
    load_cards,
    save_cards,
    validate_card,
    validate_effect,
)


OLED_BG = "#090b0d"
OLED_PANEL = "#111418"
OLED_FIELD = "#1b2026"
OLED_BORDER = "#30363d"
OLED_TEXT = "#e3e8ed"
OLED_MUTED = "#98a2ad"
OLED_ACCENT = "#5b9bd5"
PARAMETER_TYPES = ("小数", "整数", "布尔", "文本")

COMMON_PARAMETERS: dict[str, tuple[ParameterValue, str]] = {
    "chance": (0.25, "触发概率"),
    "duration": (5.0, "持续时间"),
    "interval": (1.0, "触发间隔"),
    "cooldown": (1.0, "冷却时间"),
    "threshold": (0.5, "触发阈值"),
    "cap": (1.0, "效果上限"),
    "condition_stat": ("population", "条件属性"),
    "comparison": ("greater_equal", "比较方式"),
    "condition_value": (10.0, "条件数值"),
    "scale_stat": ("population", "成长依据"),
    "step": (1.0, "每层步长"),
    "value_per_step": (0.01, "每步数值"),
    "value_per_second": (0.01, "每秒数值"),
    "triggers_per_stack": (1, "每层触发次数"),
    "value_per_stack": (0.01, "每层数值"),
    "stacks_per_trigger": (1, "每次触发增加层数"),
    "max_stacks": (10, "最大层数"),
    "clear_on_move": (False, "移动时清除层数"),
    "clear_on_world": (False, "换世界清除层数"),
    "delay": (0.0, "生效延迟"),
    "initial_value": (0.0, "首次生效数值"),
    "value_per_interval": (0.01, "每间隔数值"),
    "per_world": (0.01, "每世界数值"),
    "linger": (0.0, "效果保留时间"),
    "radius": (95.0, "作用半径"),
    "trigger_target": (TARGET_NORMAL, "命中触发对象"),
    "global_effect": (False, "是否全屏生效"),
    "boss_kind": ("big", "Boss类型"),
}


@dataclass
class ParameterEditorRow:
    frame: ttk.Frame
    key_var: tk.StringVar
    value_entry: ttk.Entry
    type_var: tk.StringVar
    required: bool


def editor_cards_path() -> Path:
    path = default_cards_path()
    if os.environ.get("DOUBLE_FRONT_CARDS") or not getattr(sys, "frozen", False):
        return path
    external = Path(sys.executable).resolve().parent / "data" / "cards.json"
    if external.exists():
        return external
    external.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, external)
    return external


def display_values(values: dict[str, str]) -> list[str]:
    return [f"{key} | {name}" for key, name in values.items()]


def display_key(value: str) -> str:
    return value.split(" | ", 1)[0]


class CardEditor(tk.Tk):
    def __init__(self, path: Path | None = None) -> None:
        super().__init__()
        self.path = path or editor_cards_path()
        self.cards = list(load_cards(self.path))
        self.filtered_indices: list[int] = []
        self.current_index: int | None = None
        self.current_effect_index: int | None = None
        self.editing_effects: list[CardEffect] = []
        self.parameter_rows: list[ParameterEditorRow] = []
        self.loading_form = False
        self.dirty = False

        self.title("双线火力 - 通用搓卡器")
        self.geometry("1420x900")
        self.minsize(1120, 760)
        self.configure(background=OLED_BG)
        self.option_add("*Font", ("Microsoft YaHei UI", 10))

        self.key_var = tk.StringVar()
        self.name_var = tk.StringVar()
        self.category_var = tk.StringVar()
        self.rarity_var = tk.StringVar(value=RARITIES[0])
        self.price_var = tk.StringVar(value="3")
        self.search_var = tk.StringVar()
        self.status_var = tk.StringVar()

        self.target_player_var = tk.BooleanVar()
        self.target_normal_var = tk.BooleanVar()
        self.target_elite_var = tk.BooleanVar()
        self.target_boss_var = tk.BooleanVar()
        self.target_gate_var = tk.BooleanVar()
        self.trigger_var = tk.StringVar()
        self.action_var = tk.StringVar()
        self.stat_var = tk.StringVar()
        self.operator_var = tk.StringVar()
        self.stacking_var = tk.StringVar()
        self.exclusive_var = tk.StringVar()
        self.priority_var = tk.StringVar(value="0")
        self.common_parameter_var = tk.StringVar()

        self._configure_theme()
        self._build_ui()
        self._bind_dirty_tracking()
        self.protocol("WM_DELETE_WINDOW", self.close_editor)
        self.bind_all("<Control-s>", lambda _event: self.save_all())
        self.refresh_card_list(select_index=0)
        self.set_status(f"已读取 {len(self.cards)} 张卡牌：{self.path}")
        self.after(0, self.enable_dark_title_bar)

    def _configure_theme(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background=OLED_BG, foreground=OLED_TEXT)
        style.configure("TFrame", background=OLED_BG)
        style.configure("Panel.TFrame", background=OLED_PANEL)
        style.configure("TLabel", background=OLED_BG, foreground=OLED_TEXT)
        style.configure("Muted.TLabel", background=OLED_BG, foreground=OLED_MUTED)
        style.configure(
            "TButton",
            background=OLED_FIELD,
            foreground=OLED_TEXT,
            bordercolor=OLED_BORDER,
            lightcolor=OLED_BORDER,
            darkcolor=OLED_BORDER,
            padding=(9, 5),
        )
        style.map("TButton", background=[("active", "#262d35"), ("pressed", "#303945")])
        style.configure("Accent.TButton", background="#244e73", foreground="#f2f7fb", bordercolor=OLED_ACCENT)
        style.map("Accent.TButton", background=[("active", "#2f6594"), ("pressed", "#1d405f")])
        style.configure(
            "TEntry",
            fieldbackground=OLED_FIELD,
            foreground=OLED_TEXT,
            insertcolor=OLED_TEXT,
            bordercolor=OLED_BORDER,
            lightcolor=OLED_BORDER,
            darkcolor=OLED_BORDER,
            padding=5,
        )
        style.map(
            "TEntry",
            fieldbackground=[("readonly", "#15191e"), ("disabled", "#15191e")],
            foreground=[("readonly", OLED_MUTED), ("disabled", "#65707a")],
        )
        style.configure(
            "TCombobox",
            fieldbackground=OLED_FIELD,
            background=OLED_FIELD,
            foreground=OLED_TEXT,
            arrowcolor=OLED_TEXT,
            bordercolor=OLED_BORDER,
            lightcolor=OLED_BORDER,
            darkcolor=OLED_BORDER,
            padding=4,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", OLED_FIELD)],
            selectbackground=[("readonly", OLED_FIELD)],
            selectforeground=[("readonly", OLED_TEXT)],
        )
        style.configure("TCheckbutton", background=OLED_BG, foreground=OLED_TEXT)
        style.map("TCheckbutton", background=[("active", OLED_BG)], foreground=[("active", "#ffffff")])
        style.configure(
            "Vertical.TScrollbar",
            background="#22282f",
            troughcolor=OLED_BG,
            bordercolor=OLED_BG,
            arrowcolor=OLED_MUTED,
        )
        style.configure("TPanedwindow", background=OLED_BG)
        style.configure("TSeparator", background=OLED_BORDER)
        self.option_add("*TCombobox*Listbox.background", OLED_FIELD)
        self.option_add("*TCombobox*Listbox.foreground", OLED_TEXT)
        self.option_add("*TCombobox*Listbox.selectBackground", "#285b85")
        self.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

    def enable_dark_title_bar(self) -> None:
        if sys.platform != "win32":
            return
        try:
            enabled = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                self.winfo_id(), 20, ctypes.byref(enabled), ctypes.sizeof(enabled)
            )
        except (AttributeError, OSError):
            pass

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self, padding=(12, 10))
        toolbar.pack(fill=tk.X)
        ttk.Label(toolbar, text="统一卡牌文件：").pack(side=tk.LEFT)
        ttk.Label(toolbar, text=str(self.path), style="Muted.TLabel").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(toolbar, text="重新读取", command=self.reload_all).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(toolbar, text="保存全部  Ctrl+S", command=self.save_all, style="Accent.TButton").pack(side=tk.RIGHT)
        ttk.Separator(self).pack(fill=tk.X)

        main_pane = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)
        left = ttk.Frame(main_pane, padding=(4, 4, 10, 4))
        right = ttk.Frame(main_pane, padding=(12, 4, 4, 4))
        main_pane.add(left, weight=1)
        main_pane.add(right, weight=4)

        ttk.Label(left, text="卡牌库", font=("Microsoft YaHei UI", 14, "bold")).pack(anchor=tk.W)
        ttk.Entry(left, textvariable=self.search_var).pack(fill=tk.X, pady=(10, 8))
        list_frame = ttk.Frame(left)
        list_frame.pack(fill=tk.BOTH, expand=True)
        self.card_list = self._dark_listbox(list_frame)
        card_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.card_list.yview)
        self.card_list.configure(yscrollcommand=card_scroll.set)
        self.card_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        card_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.card_list.bind("<<ListboxSelect>>", self.select_card)
        card_buttons = ttk.Frame(left)
        card_buttons.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(card_buttons, text="新建", command=self.add_card).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(card_buttons, text="复制", command=self.copy_card).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(card_buttons, text="删除", command=self.delete_card).pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._build_card_form(right)
        ttk.Separator(right).pack(fill=tk.X, pady=(12, 10))
        self._build_effect_area(right)

        ttk.Label(
            self,
            textvariable=self.status_var,
            anchor=tk.W,
            padding=(10, 7),
            background=OLED_PANEL,
            foreground=OLED_MUTED,
        ).pack(fill=tk.X, side=tk.BOTTOM)

    def _dark_listbox(self, parent: tk.Widget, height: int = 10) -> tk.Listbox:
        return tk.Listbox(
            parent,
            height=height,
            activestyle="none",
            exportselection=False,
            background=OLED_PANEL,
            foreground=OLED_TEXT,
            selectbackground="#285b85",
            selectforeground="#ffffff",
            highlightbackground=OLED_BORDER,
            highlightcolor=OLED_ACCENT,
            relief=tk.FLAT,
            borderwidth=0,
        )

    def _build_card_form(self, parent: ttk.Frame) -> None:
        heading = ttk.Frame(parent)
        heading.pack(fill=tk.X)
        ttk.Label(heading, text="卡牌基础信息", font=("Microsoft YaHei UI", 14, "bold")).pack(side=tk.LEFT)
        ttk.Button(heading, text="应用当前修改", command=self.apply_current).pack(side=tk.RIGHT)

        form = ttk.Frame(parent)
        form.pack(fill=tk.X, pady=(8, 0))
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)
        fields = (
            ("唯一键名", self.key_var, 0, 0),
            ("卡牌名称", self.name_var, 0, 2),
            ("价格", self.price_var, 1, 2),
        )
        for label, variable, row, column in fields:
            ttk.Label(form, text=label).grid(row=row, column=column, sticky=tk.W, pady=4)
            ttk.Entry(form, textvariable=variable).grid(
                row=row, column=column + 1, sticky=tk.EW, padx=(8, 18 if column == 0 else 0), pady=4
            )

        ttk.Label(form, text="类别").grid(row=1, column=0, sticky=tk.W, pady=4)
        self.category_combo = ttk.Combobox(
            form,
            textvariable=self.category_var,
            values=display_values(CATEGORY_SPECS),
            state="readonly",
        )
        self.category_combo.grid(row=1, column=1, sticky=tk.EW, padx=(8, 18), pady=4)
        ttk.Label(form, text="稀有度").grid(row=2, column=0, sticky=tk.W, pady=4)
        ttk.Combobox(form, textvariable=self.rarity_var, values=RARITIES, state="readonly").grid(
            row=2, column=1, sticky=tk.EW, padx=(8, 18), pady=4
        )

        ttk.Label(form, text="商店描述").grid(row=3, column=0, columnspan=4, sticky=tk.W, pady=(8, 4))
        self.description_text = tk.Text(
            form,
            height=3,
            wrap=tk.WORD,
            undo=True,
            background=OLED_FIELD,
            foreground=OLED_TEXT,
            insertbackground=OLED_TEXT,
            selectbackground="#285b85",
            selectforeground="#ffffff",
            highlightbackground=OLED_BORDER,
            highlightcolor=OLED_ACCENT,
            relief=tk.FLAT,
            padx=8,
            pady=7,
        )
        self.description_text.grid(row=4, column=0, columnspan=4, sticky=tk.EW)

    def _build_effect_area(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="效果列表", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor=tk.W)
        effect_pane = ttk.Panedwindow(parent, orient=tk.HORIZONTAL)
        effect_pane.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        effect_left = ttk.Frame(effect_pane, padding=(0, 0, 10, 0))
        effect_right = ttk.Frame(effect_pane, padding=(12, 0, 0, 0))
        effect_pane.add(effect_left, weight=1)
        effect_pane.add(effect_right, weight=4)

        effect_list_frame = ttk.Frame(effect_left)
        effect_list_frame.pack(fill=tk.BOTH, expand=True)
        self.effect_list = self._dark_listbox(effect_list_frame, height=12)
        effect_scroll = ttk.Scrollbar(effect_list_frame, orient=tk.VERTICAL, command=self.effect_list.yview)
        self.effect_list.configure(yscrollcommand=effect_scroll.set)
        self.effect_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        effect_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.effect_list.bind("<<ListboxSelect>>", self.select_effect)
        effect_buttons = ttk.Frame(effect_left)
        effect_buttons.pack(fill=tk.X, pady=(7, 0))
        ttk.Button(effect_buttons, text="新增效果", command=self.add_effect).pack(fill=tk.X)
        ttk.Button(effect_buttons, text="复制", command=self.copy_effect).pack(side=tk.LEFT, fill=tk.X, expand=True, pady=(5, 0))
        ttk.Button(effect_buttons, text="删除", command=self.delete_effect).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0), pady=(5, 0)
        )

        self._build_effect_form(effect_right)

    def _build_effect_form(self, form: ttk.Frame) -> None:
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)

        ttk.Label(form, text="作用对象", font=("Microsoft YaHei UI", 10, "bold")).grid(row=0, column=0, sticky=tk.W)
        targets = ttk.Frame(form)
        targets.grid(row=0, column=1, columnspan=3, sticky=tk.EW, padx=(8, 0))
        ttk.Checkbutton(targets, text="玩家 (0)", variable=self.target_player_var).pack(side=tk.LEFT)
        ttk.Separator(targets, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        ttk.Checkbutton(targets, text="小怪 (2)", variable=self.target_normal_var).pack(side=tk.LEFT)
        ttk.Checkbutton(targets, text="精英 (4)", variable=self.target_elite_var).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Checkbutton(targets, text="Boss (8)", variable=self.target_boss_var).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Separator(targets, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        ttk.Checkbutton(targets, text="门 (21)", variable=self.target_gate_var).pack(side=tk.LEFT)

        self.trigger_combo = self._labeled_combo(form, "触发时机", self.trigger_var, display_values(TRIGGER_SPECS), 1, 0)
        self.trigger_combo.bind("<<ComboboxSelected>>", self.change_trigger)
        self.action_combo = self._labeled_combo(form, "效果行为", self.action_var, display_values(ACTION_SPECS), 1, 2)
        self.action_combo.bind("<<ComboboxSelected>>", self.change_action)
        self.stat_combo = self._labeled_combo(form, "作用属性", self.stat_var, [], 2, 0)
        self.operator_combo = self._labeled_combo(form, "运算方式", self.operator_var, display_values(OPERATOR_SPECS), 2, 2)
        self.stacking_combo = self._labeled_combo(form, "叠加规则", self.stacking_var, display_values(STACKING_SPECS), 3, 0)

        ttk.Label(form, text="互斥组").grid(row=3, column=2, sticky=tk.W, pady=3)
        ttk.Entry(form, textvariable=self.exclusive_var).grid(row=3, column=3, sticky=tk.EW, padx=(8, 0), pady=3)
        ttk.Label(form, text="优先级").grid(row=4, column=0, sticky=tk.W, pady=3)
        ttk.Entry(form, textvariable=self.priority_var).grid(row=4, column=1, sticky=tk.EW, padx=(8, 18), pady=3)

        parameter_toolbar = ttk.Frame(form)
        parameter_toolbar.grid(row=5, column=0, columnspan=4, sticky=tk.EW, pady=(9, 4))
        ttk.Label(parameter_toolbar, text="效果参数", font=("Microsoft YaHei UI", 10, "bold")).pack(side=tk.LEFT)
        common_values = [f"{key} | {label}" for key, (_, label) in COMMON_PARAMETERS.items()]
        self.common_parameter_combo = ttk.Combobox(
            parameter_toolbar,
            textvariable=self.common_parameter_var,
            values=common_values,
            state="readonly",
            width=24,
        )
        self.common_parameter_combo.pack(side=tk.LEFT, padx=(12, 5))
        ttk.Button(parameter_toolbar, text="添加常用参数", command=self.add_common_parameter).pack(side=tk.LEFT)
        ttk.Button(parameter_toolbar, text="+ 自定义参数", command=self.add_custom_parameter).pack(side=tk.LEFT, padx=(5, 0))

        parameter_canvas = tk.Canvas(form, highlightthickness=0, background=OLED_BG)
        parameter_scroll = ttk.Scrollbar(form, orient=tk.VERTICAL, command=parameter_canvas.yview)
        parameter_canvas.configure(yscrollcommand=parameter_scroll.set)
        parameter_canvas.grid(row=6, column=0, columnspan=4, sticky=tk.NSEW)
        parameter_scroll.grid(row=6, column=4, sticky=tk.NS)
        form.rowconfigure(6, weight=1)
        self.parameter_frame = ttk.Frame(parameter_canvas)
        parameter_window = parameter_canvas.create_window((0, 0), window=self.parameter_frame, anchor=tk.NW)
        self.parameter_frame.bind(
            "<Configure>",
            lambda _event: parameter_canvas.configure(scrollregion=parameter_canvas.bbox("all")),
        )
        parameter_canvas.bind(
            "<Configure>",
            lambda event: parameter_canvas.itemconfigure(parameter_window, width=event.width),
        )

    def _labeled_combo(
        self,
        parent: ttk.Frame,
        label: str,
        variable: tk.StringVar,
        values: list[str],
        row: int,
        column: int,
    ) -> ttk.Combobox:
        ttk.Label(parent, text=label).grid(row=row, column=column, sticky=tk.W, pady=3)
        combo = ttk.Combobox(parent, textvariable=variable, values=values, state="readonly")
        combo.grid(row=row, column=column + 1, sticky=tk.EW, padx=(8, 18 if column == 0 else 0), pady=3)
        return combo

    def _bind_dirty_tracking(self) -> None:
        self.search_var.trace_add("write", lambda *_: self.refresh_card_list())
        variables = (
            self.key_var,
            self.name_var,
            self.category_var,
            self.rarity_var,
            self.price_var,
            self.target_player_var,
            self.target_normal_var,
            self.target_elite_var,
            self.target_boss_var,
            self.target_gate_var,
            self.trigger_var,
            self.action_var,
            self.stat_var,
            self.operator_var,
            self.stacking_var,
            self.exclusive_var,
            self.priority_var,
        )
        for variable in variables:
            variable.trace_add("write", self.mark_dirty)
        for variable in (
            self.target_player_var,
            self.target_normal_var,
            self.target_elite_var,
            self.target_boss_var,
            self.target_gate_var,
        ):
            variable.trace_add("write", self.targets_changed)
        self.description_text.bind("<KeyRelease>", self.mark_dirty)

    @staticmethod
    def parameter_type(value: ParameterValue) -> str:
        if isinstance(value, bool):
            return "布尔"
        if isinstance(value, int):
            return "整数"
        if isinstance(value, float):
            return "小数"
        return "文本"

    @staticmethod
    def parse_parameter(text: str, parameter_type: str) -> ParameterValue:
        value = text.strip()
        if parameter_type == "布尔":
            if value.lower() in {"true", "1", "是"}:
                return True
            if value.lower() in {"false", "0", "否"}:
                return False
            raise ValueError("布尔参数只能填写 true/false、1/0 或 是/否")
        if parameter_type == "整数":
            number = float(value)
            if not number.is_integer():
                raise ValueError("该参数必须是整数")
            return int(number)
        if parameter_type == "小数":
            return float(value)
        if parameter_type == "文本":
            return value
        raise ValueError(f"未知参数类型：{parameter_type}")

    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    def mark_dirty(self, *_args: object) -> None:
        if not self.loading_form and self.current_index is not None:
            self.dirty = True

    def refresh_card_list(self, select_index: int | None = None) -> None:
        query = self.search_var.get().strip().lower()
        self.filtered_indices = [
            index
            for index, card in enumerate(self.cards)
            if not query or query in card.key.lower() or query in card.name.lower()
        ]
        self.loading_form = True
        self.card_list.delete(0, tk.END)
        for index in self.filtered_indices:
            card = self.cards[index]
            category = CATEGORY_SPECS[card.category]
            self.card_list.insert(tk.END, f"[{category}/{card.rarity}] {card.name} ({card.key})")
        if select_index is not None and select_index in self.filtered_indices:
            position = self.filtered_indices.index(select_index)
            self.card_list.selection_set(position)
            self.card_list.see(position)
            self.load_card_form(select_index)
        elif self.filtered_indices and self.current_index not in self.filtered_indices:
            self.card_list.selection_set(0)
            self.load_card_form(self.filtered_indices[0])
        self.loading_form = False

    def select_card(self, _event: tk.Event | None = None) -> None:
        if self.loading_form or not self.card_list.curselection():
            return
        index = self.filtered_indices[self.card_list.curselection()[0]]
        if self.current_index is not None and index != self.current_index:
            try:
                self.update_card_from_form(self.current_index)
            except ValueError as error:
                messagebox.showerror("当前卡牌无法应用", str(error), parent=self)
                self.refresh_card_list(select_index=self.current_index)
                return
        self.load_card_form(index)

    def load_card_form(self, index: int) -> None:
        card = self.cards[index]
        self.current_index = index
        self.loading_form = True
        self.key_var.set(card.key)
        self.name_var.set(card.name)
        self.category_var.set(f"{card.category} | {CATEGORY_SPECS[card.category]}")
        self.rarity_var.set(card.rarity)
        self.price_var.set(str(card.price))
        self.description_text.delete("1.0", tk.END)
        self.description_text.insert("1.0", card.description)
        self.editing_effects = [replace(effect, parameters=dict(effect.parameters)) for effect in card.effects]
        self.refresh_effect_list(select_index=0 if self.editing_effects else None)
        self.loading_form = False

    def effect_label(self, index: int, effect: CardEffect) -> str:
        return f"{index + 1}. {ACTION_SPECS[effect.action]} / {STAT_SPECS[effect.stat]}"

    def refresh_effect_list(self, select_index: int | None = None) -> None:
        previous_loading = self.loading_form
        self.loading_form = True
        self.effect_list.delete(0, tk.END)
        for index, effect in enumerate(self.editing_effects):
            self.effect_list.insert(tk.END, self.effect_label(index, effect))
        if select_index is not None and 0 <= select_index < len(self.editing_effects):
            self.effect_list.selection_set(select_index)
            self.effect_list.see(select_index)
            self.load_effect_form(select_index)
        else:
            self.current_effect_index = None
            self.load_empty_effect_form()
        self.loading_form = previous_loading

    def select_effect(self, _event: tk.Event | None = None) -> None:
        if self.loading_form or not self.effect_list.curselection():
            return
        index = self.effect_list.curselection()[0]
        if self.current_effect_index is not None and index != self.current_effect_index:
            try:
                self.apply_current_effect()
            except ValueError as error:
                messagebox.showerror("当前效果无法应用", str(error), parent=self)
                self.refresh_effect_list(select_index=self.current_effect_index)
                return
        self.load_effect_form(index)

    def load_effect_form(self, index: int) -> None:
        effect = self.editing_effects[index]
        self.current_effect_index = index
        previous_loading = self.loading_form
        self.loading_form = True
        self.target_player_var.set(effect.targets.player)
        self.target_normal_var.set(TARGET_NORMAL in effect.targets.enemies)
        self.target_elite_var.set(TARGET_ELITE in effect.targets.enemies)
        self.target_boss_var.set(TARGET_BOSS in effect.targets.enemies)
        self.target_gate_var.set(effect.targets.gate)
        self.action_var.set(f"{effect.action} | {ACTION_SPECS[effect.action]}")
        self.update_trigger_options(effect.action, effect.trigger)
        self.update_stat_options(effect.action, effect.stat)
        self.operator_var.set(f"{effect.operator} | {OPERATOR_SPECS[effect.operator]}")
        self.stacking_var.set(f"{effect.stacking} | {STACKING_SPECS[effect.stacking]}")
        self.exclusive_var.set(effect.exclusive_group)
        self.priority_var.set(str(effect.priority))
        self.build_parameter_form(effect.action, effect.parameters)
        self.loading_form = previous_loading

    def load_empty_effect_form(self) -> None:
        previous_loading = self.loading_form
        self.loading_form = True
        for variable in (
            self.target_player_var,
            self.target_normal_var,
            self.target_elite_var,
            self.target_boss_var,
            self.target_gate_var,
        ):
            variable.set(False)
        self.action_var.set("modify_stat | 修改属性")
        self.update_trigger_options("modify_stat", "passive")
        self.update_stat_options("modify_stat", ACTION_STATS["modify_stat"][0])
        self.operator_var.set("add_flat | 固定加减")
        self.stacking_var.set("add | 相加")
        self.exclusive_var.set("")
        self.priority_var.set("0")
        self.build_parameter_form("modify_stat", action_defaults("modify_stat"))
        self.loading_form = previous_loading

    def update_stat_options(self, action: str, selected: str | None = None) -> None:
        selected_targets = self.selected_target_ids()
        compatible = [
            key
            for key in ACTION_STATS[action]
            if not selected_targets or selected_targets <= set(STAT_TARGETS[key])
        ]
        values = [f"{key} | {STAT_SPECS[key]}" for key in compatible]
        self.stat_combo.configure(values=values)
        chosen = selected if selected in compatible else (compatible[0] if compatible else "")
        self.stat_var.set(f"{chosen} | {STAT_SPECS[chosen]}" if chosen else "")

    def selected_target_ids(self) -> set[int]:
        selected = {
            target
            for target, variable in (
                (TARGET_PLAYER, self.target_player_var),
                (TARGET_NORMAL, self.target_normal_var),
                (TARGET_ELITE, self.target_elite_var),
                (TARGET_BOSS, self.target_boss_var),
                (TARGET_GATE, self.target_gate_var),
            )
            if variable.get()
        }
        return selected

    def targets_changed(self, *_args: object) -> None:
        if self.loading_form or self.current_effect_index is None:
            return
        action = display_key(self.action_var.get())
        if not action:
            return
        selected = display_key(self.stat_var.get())
        self.loading_form = True
        self.update_stat_options(action, selected)
        self.loading_form = False
        if not self.stat_var.get():
            self.set_status("当前作用对象组合没有可用属性，请调整对象或效果行为")

    def update_trigger_options(self, action: str, selected: str | None = None) -> None:
        values = [f"{key} | {TRIGGER_SPECS[key]}" for key in ACTION_TRIGGERS[action]]
        self.trigger_combo.configure(values=values)
        chosen = selected if selected in ACTION_TRIGGERS[action] else ACTION_TRIGGERS[action][0]
        self.trigger_var.set(f"{chosen} | {TRIGGER_SPECS[chosen]}")

    def build_parameter_form(self, action: str, values: dict[str, ParameterValue]) -> None:
        for child in self.parameter_frame.winfo_children():
            child.destroy()
        self.parameter_rows.clear()
        header = ttk.Frame(self.parameter_frame)
        header.pack(fill=tk.X, pady=(2, 4))
        header.columnconfigure(1, weight=1)
        ttk.Label(header, text="参数键", width=25, style="Muted.TLabel").grid(row=0, column=0, sticky=tk.W)
        ttk.Label(header, text="参数值", style="Muted.TLabel").grid(row=0, column=1, sticky=tk.W, padx=6)
        ttk.Label(header, text="类型", width=8, style="Muted.TLabel").grid(row=0, column=2, sticky=tk.W, padx=6)
        ttk.Label(header, text="操作", width=7, style="Muted.TLabel").grid(row=0, column=3, sticky=tk.W)

        defaults = ACTION_PARAMETER_DEFAULTS[action]
        for key, default in defaults.items():
            value = values.get(key, default)
            self.add_parameter_row(key, value, self.parameter_type(value), required=True)
        for key, value in values.items():
            if key not in defaults:
                self.add_parameter_row(key, value, self.parameter_type(value), required=False)

    def add_parameter_row(
        self,
        key: str,
        value: ParameterValue | str,
        parameter_type: str,
        required: bool,
    ) -> None:
        frame = ttk.Frame(self.parameter_frame)
        frame.pack(fill=tk.X, pady=3)
        frame.columnconfigure(1, weight=1)
        key_var = tk.StringVar(value=key)
        key_entry = ttk.Entry(frame, textvariable=key_var, width=25)
        key_entry.grid(row=0, column=0, sticky=tk.EW)
        if required:
            key_entry.configure(state="readonly")
        value_entry = ttk.Entry(frame)
        value_entry.insert(0, str(value))
        value_entry.grid(row=0, column=1, sticky=tk.EW, padx=6)
        type_var = tk.StringVar(value=parameter_type)
        type_box = ttk.Combobox(frame, textvariable=type_var, values=PARAMETER_TYPES, width=7, state="readonly")
        type_box.grid(row=0, column=2, sticky=tk.EW, padx=6)
        row = ParameterEditorRow(frame, key_var, value_entry, type_var, required)
        self.parameter_rows.append(row)
        if required:
            ttk.Label(frame, text="模板", width=7, style="Muted.TLabel").grid(row=0, column=3, sticky=tk.W)
        else:
            ttk.Button(frame, text="删除", command=lambda: self.delete_parameter(row)).grid(row=0, column=3, sticky=tk.EW)
        key_var.trace_add("write", self.mark_dirty)
        type_var.trace_add("write", self.mark_dirty)
        value_entry.bind("<KeyRelease>", self.mark_dirty)

    def change_action(self, _event: tk.Event | None = None) -> None:
        if self.loading_form or self.current_effect_index is None:
            return
        extras = [
            (row.key_var.get(), row.value_entry.get(), row.type_var.get())
            for row in self.parameter_rows
            if not row.required
        ]
        action = display_key(self.action_var.get())
        self.loading_form = True
        self.update_trigger_options(action)
        self.update_stat_options(action)
        self.build_parameter_form(action, action_defaults(action))
        for key, value, value_type in extras:
            self.add_parameter_row(key, value, value_type, required=False)
        self.loading_form = False
        self.dirty = True
        self.set_status(f"已切换为“{ACTION_SPECS[action]}”，模板参数已重置，附加参数已保留")

    def change_trigger(self, _event: tk.Event | None = None) -> None:
        if self.loading_form or self.current_effect_index is None:
            return
        action = display_key(self.action_var.get())
        trigger = display_key(self.trigger_var.get())
        if action != "modify_stat":
            return
        additions: list[str] = []
        keys = self.parameter_keys()
        if trigger == "interval" and "interval" not in keys:
            additions.append("interval")
        if (trigger.startswith("on_") or trigger == "interval") and not {
            "duration",
            "triggers_per_stack",
            "stacks_per_trigger",
        }.intersection(keys):
            additions.append("duration")
        for key in additions:
            value, _ = COMMON_PARAMETERS[key]
            self.add_parameter_row(key, value, self.parameter_type(value), required=False)
        if additions:
            self.set_status(f"已为触发器自动添加参数：{', '.join(additions)}")

    def parameter_keys(self) -> set[str]:
        return {row.key_var.get().strip() for row in self.parameter_rows}

    def add_common_parameter(self) -> None:
        if self.current_effect_index is None:
            return
        key = display_key(self.common_parameter_var.get())
        if not key:
            self.set_status("请先在下拉框选择一个常用参数")
            return
        if key in self.parameter_keys():
            self.set_status(f"参数 {key} 已存在")
            return
        value, label = COMMON_PARAMETERS[key]
        self.add_parameter_row(key, value, self.parameter_type(value), required=False)
        self.dirty = True
        self.set_status(f"已添加 {key}（{label}）")

    def add_custom_parameter(self) -> None:
        if self.current_effect_index is None:
            return
        existing = self.parameter_keys()
        key = "custom_parameter"
        suffix = 2
        while key in existing:
            key = f"custom_parameter_{suffix}"
            suffix += 1
        self.add_parameter_row(key, 0.0, "小数", required=False)
        self.dirty = True
        self.set_status("已新增自定义参数；只有通用解释器识别的参数名会改变游戏行为")

    def delete_parameter(self, row: ParameterEditorRow) -> None:
        if row.required:
            return
        row.frame.destroy()
        self.parameter_rows.remove(row)
        self.dirty = True

    def collect_parameters(self) -> dict[str, ParameterValue]:
        parameters: dict[str, ParameterValue] = {}
        for row in self.parameter_rows:
            key = row.key_var.get().strip()
            if not key:
                raise ValueError("参数键不能为空")
            if key in parameters:
                raise ValueError(f"参数键重复：{key}")
            try:
                parameters[key] = self.parse_parameter(row.value_entry.get(), row.type_var.get())
            except ValueError as error:
                raise ValueError(f"参数 {key} 的值无效：{error}") from error
        return parameters

    def collect_effect(self) -> CardEffect:
        try:
            priority = int(self.priority_var.get().strip())
        except ValueError as error:
            raise ValueError("效果优先级必须是整数") from error
        enemies = tuple(
            target
            for target, selected in (
                (TARGET_NORMAL, self.target_normal_var.get()),
                (TARGET_ELITE, self.target_elite_var.get()),
                (TARGET_BOSS, self.target_boss_var.get()),
            )
            if selected
        )
        return CardEffect(
            targets=EffectTargets(self.target_player_var.get(), enemies, self.target_gate_var.get()),
            trigger=display_key(self.trigger_var.get()),
            action=display_key(self.action_var.get()),
            stat=display_key(self.stat_var.get()),
            operator=display_key(self.operator_var.get()),
            stacking=display_key(self.stacking_var.get()),
            exclusive_group=self.exclusive_var.get().strip(),
            priority=priority,
            parameters=self.collect_parameters(),
        )

    def apply_current_effect(self) -> None:
        if self.current_effect_index is None:
            return
        effect = self.collect_effect()
        validate_effect(effect, self.key_var.get().strip() or "new_card", self.current_effect_index)
        self.editing_effects[self.current_effect_index] = effect

    def add_effect(self) -> None:
        try:
            self.apply_current_effect()
        except ValueError as error:
            messagebox.showerror("当前效果无法应用", str(error), parent=self)
            return
        effect = CardEffect(
            EffectTargets(player=True),
            "passive",
            "modify_stat",
            "base_damage",
            "add_flat",
            "add",
            "",
            0,
            action_defaults("modify_stat"),
        )
        self.editing_effects.append(effect)
        self.dirty = True
        self.refresh_effect_list(select_index=len(self.editing_effects) - 1)
        self.set_status("已新增效果块；可组合目标、触发时机、行为、属性、运算和参数")

    def copy_effect(self) -> None:
        if self.current_effect_index is None:
            return
        try:
            self.apply_current_effect()
        except ValueError as error:
            messagebox.showerror("当前效果无法应用", str(error), parent=self)
            return
        source = self.editing_effects[self.current_effect_index]
        self.editing_effects.append(replace(source, parameters=dict(source.parameters)))
        self.dirty = True
        self.refresh_effect_list(select_index=len(self.editing_effects) - 1)

    def delete_effect(self) -> None:
        if self.current_effect_index is None:
            return
        index = self.current_effect_index
        self.editing_effects.pop(index)
        self.current_effect_index = None
        self.dirty = True
        next_index = min(index, len(self.editing_effects) - 1) if self.editing_effects else None
        self.refresh_effect_list(select_index=next_index)

    def collect_card(self) -> Card:
        self.apply_current_effect()
        try:
            price = int(self.price_var.get().strip())
        except ValueError as error:
            raise ValueError("价格必须是整数") from error
        return Card(
            key=self.key_var.get().strip(),
            name=self.name_var.get().strip(),
            description=self.description_text.get("1.0", "end-1c").strip(),
            rarity=self.rarity_var.get(),
            price=price,
            category=display_key(self.category_var.get()),
            effects=tuple(self.editing_effects),
        )

    def update_card_from_form(self, index: int) -> None:
        card = self.collect_card()
        validate_card(card)
        if any(other.key == card.key for position, other in enumerate(self.cards) if position != index):
            raise ValueError(f"唯一键名重复：{card.key}")
        if card != self.cards[index]:
            self.cards[index] = card
            self.dirty = True

    def apply_current(self) -> None:
        if self.current_index is None:
            return
        try:
            self.update_card_from_form(self.current_index)
        except ValueError as error:
            messagebox.showerror("无法应用", str(error), parent=self)
            return
        self.refresh_card_list(select_index=self.current_index)
        self.set_status("当前卡牌和全部效果已应用；点击“保存全部”写入统一卡牌文件")

    def prepare_card_change(self) -> bool:
        if self.current_index is None:
            return True
        try:
            self.update_card_from_form(self.current_index)
            return True
        except ValueError as error:
            messagebox.showerror("当前卡牌无法应用", str(error), parent=self)
            return False

    def unique_key(self, seed: str) -> str:
        existing = {card.key for card in self.cards}
        if seed not in existing:
            return seed
        suffix = 2
        while f"{seed}_{suffix}" in existing:
            suffix += 1
        return f"{seed}_{suffix}"

    def add_card(self) -> None:
        if not self.prepare_card_change():
            return
        self.cards.append(
            Card(
                self.unique_key("new_card"),
                "新卡牌",
                "请填写这张卡牌在商店中显示的描述。",
                "普通",
                3,
                "custom",
                (),
            )
        )
        self.dirty = True
        self.search_var.set("")
        self.refresh_card_list(select_index=len(self.cards) - 1)

    def copy_card(self) -> None:
        if self.current_index is None or not self.prepare_card_change():
            return
        source = self.cards[self.current_index]
        effects = tuple(replace(effect, parameters=dict(effect.parameters)) for effect in source.effects)
        self.cards.append(
            replace(source, key=self.unique_key(f"{source.key}_copy"), name=f"{source.name} 副本", effects=effects)
        )
        self.dirty = True
        self.search_var.set("")
        self.refresh_card_list(select_index=len(self.cards) - 1)

    def delete_card(self) -> None:
        if self.current_index is None:
            return
        card = self.cards[self.current_index]
        if not messagebox.askyesno("删除卡牌", f"确定删除“{card.name}”吗？", parent=self):
            return
        index = self.current_index
        self.cards.pop(index)
        self.current_index = None
        self.dirty = True
        next_index = min(index, len(self.cards) - 1) if self.cards else None
        self.refresh_card_list(select_index=next_index)

    def save_all(self) -> None:
        if self.current_index is not None:
            try:
                self.update_card_from_form(self.current_index)
            except ValueError as error:
                messagebox.showerror("无法保存", str(error), parent=self)
                return
        try:
            save_cards(self.cards, self.path)
        except (OSError, ValueError) as error:
            messagebox.showerror("保存失败", str(error), parent=self)
            return
        self.dirty = False
        self.refresh_card_list(select_index=self.current_index)
        effect_count = sum(len(card.effects) for card in self.cards)
        self.set_status(f"已保存 {len(self.cards)} 张卡牌、{effect_count} 个效果；重启游戏后生效")

    def reload_all(self) -> None:
        if self.dirty and not messagebox.askyesno("放弃修改", "放弃尚未保存的修改并重新读取文件？", parent=self):
            return
        try:
            self.cards = list(load_cards(self.path))
        except (OSError, ValueError) as error:
            messagebox.showerror("读取失败", str(error), parent=self)
            return
        self.current_index = None
        self.current_effect_index = None
        self.dirty = False
        self.search_var.set("")
        self.refresh_card_list(select_index=0 if self.cards else None)

    def close_editor(self) -> None:
        if self.dirty:
            answer = messagebox.askyesnocancel("尚未保存", "保存全部修改后退出？", parent=self)
            if answer is None:
                return
            if answer:
                self.save_all()
                if self.dirty:
                    return
        self.destroy()


def main() -> None:
    CardEditor().mainloop()


if __name__ == "__main__":
    main()
