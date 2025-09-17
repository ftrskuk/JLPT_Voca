import csv
import json
import random
import sys
import time
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

CONFIG_PATH = Path(__file__).with_name("config.json")
WORDS_PATH = Path(__file__).with_name("words.json")
ICON_PNG_PATH = Path(__file__).with_name("icon.png")
ICON_ICO_PATH = Path(__file__).with_name("icon.ico")

DEFAULT_CONFIG = {
    "showMeaningTimer": 3,
    "nextWordTimer": 5,
    "alwaysOnTop": True,
}


def _clean_word_entries(raw_entries, source_name):
    cleaned = []
    for item in raw_entries:
        if not isinstance(item, dict):
            continue
        word = str(item.get("word", "")).strip()
        reading = str(item.get("reading", "")).strip()
        meaning = str(item.get("meaning", "")).strip()
        if word and reading and meaning:
            cleaned.append({"word": word, "reading": reading, "meaning": meaning})

    if not cleaned:
        raise ValueError(f"{source_name}에서 유효한 단어 항목을 찾을 수 없습니다.")

    return cleaned


def detach_console_window():
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        get_console_window = kernel32.GetConsoleWindow
        get_console_window.restype = ctypes.c_void_p
        hwnd = get_console_window()
        if not hwnd:
            return
        get_console_process_list = kernel32.GetConsoleProcessList
        get_console_process_list.argtypes = [ctypes.POINTER(ctypes.c_ulong), ctypes.c_ulong]
        get_console_process_list.restype = ctypes.c_ulong
        process_ids = (ctypes.c_ulong * 1)()
        count = get_console_process_list(process_ids, 1)
        if count <= 1:
            kernel32.FreeConsole()
    except Exception:
        pass


def parse_positive_int(value, fallback):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return number if number > 0 else fallback


class ConfigManager:
    def __init__(self, path: Path):
        self.path = path
        self.data = self._load()

    def _load(self):
        if not self.path.exists():
            data = DEFAULT_CONFIG.copy()
            self.save(data)
            return data
        try:
            with self.path.open("r", encoding="utf-8") as config_file:
                raw = json.load(config_file)
        except (OSError, json.JSONDecodeError):
            data = DEFAULT_CONFIG.copy()
            self.save(data)
            return data

        return self._merge_with_defaults(raw)

    def _merge_with_defaults(self, raw):
        data = DEFAULT_CONFIG.copy()
        if isinstance(raw, dict):
            data["showMeaningTimer"] = parse_positive_int(
                raw.get("showMeaningTimer"), data["showMeaningTimer"]
            )
            data["nextWordTimer"] = parse_positive_int(
                raw.get("nextWordTimer"), data["nextWordTimer"]
            )
            always_on_top = raw.get("alwaysOnTop")
            if isinstance(always_on_top, bool):
                data["alwaysOnTop"] = always_on_top
        return data

    def save(self, data=None):
        if data is not None:
            self.data = self._merge_with_defaults(data)
        with self.path.open("w", encoding="utf-8") as config_file:
            json.dump(self.data, config_file, indent=2, ensure_ascii=False)

    def update(self, show_meaning_timer: int, next_word_timer: int, always_on_top: bool):
        self.data["showMeaningTimer"] = parse_positive_int(
            show_meaning_timer, DEFAULT_CONFIG["showMeaningTimer"]
        )
        self.data["nextWordTimer"] = parse_positive_int(
            next_word_timer, DEFAULT_CONFIG["nextWordTimer"]
        )
        self.data["alwaysOnTop"] = bool(always_on_top)
        self.save()


def load_words(path: Path):
    try:
        with path.open("r", encoding="utf-8") as words_file:
            raw_words = json.load(words_file)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"{path.name} 파일을 찾을 수 없습니다.") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path.name} 형식이 올바르지 않습니다.") from exc

    if not isinstance(raw_words, list):
        raise ValueError(f"{path.name}에는 단어 객체 배열이 필요합니다.")

    return _clean_word_entries(raw_words, path.name)


def load_words_from_csv(path: Path):
    try:
        with path.open("r", encoding="utf-8", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            if reader.fieldnames is None:
                raise ValueError(f"{path.name}에 헤더 행이 필요합니다.")
            header_map = {}
            for name in reader.fieldnames:
                if not name:
                    continue
                normalized = name.strip().lstrip("\ufeff").lower()
                if normalized:
                    header_map[normalized] = name
            required = {"word", "reading", "meaning"}
            if not required.issubset(header_map):
                raise ValueError(
                    f"{path.name}에는 word, reading, meaning 헤더가 모두 포함되어야 합니다."
                )
            rows = []
            for row in reader:
                rows.append(
                    {
                        "word": row.get(header_map["word"], ""),
                        "reading": row.get(header_map["reading"], ""),
                        "meaning": row.get(header_map["meaning"], ""),
                    }
                )
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"{path.name} 파일을 찾을 수 없습니다.") from exc
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path.name}을(를) UTF-8로 읽을 수 없습니다.") from exc
    except csv.Error as exc:
        raise ValueError(f"{path.name} CSV 내용을 해석할 수 없습니다: {exc}") from exc
    except OSError as exc:
        raise OSError(f"{path.name} 파일을 열 수 없습니다: {exc}") from exc

    return _clean_word_entries(rows, path.name)


def save_words(path: Path, words):
    with path.open("w", encoding="utf-8") as words_file:
        json.dump(words, words_file, ensure_ascii=False, indent=2)


class SettingsWindow(tk.Toplevel):
    def __init__(self, app: "WordCyclerApp"):
        super().__init__(app.root)
        self.app = app
        self.title("설정")
        self.resizable(True, True)
        self.transient(app.root)
        self.grab_set()

        self.show_meaning_var = tk.StringVar(value=str(app.config_manager.data["showMeaningTimer"]))
        self.next_word_var = tk.StringVar(value=str(app.config_manager.data["nextWordTimer"]))
        self.always_on_top_var = tk.BooleanVar(value=app.config_manager.data["alwaysOnTop"])
        self.words_data = [dict(item) for item in app.get_all_words()]

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.focus()
        self.update_idletasks()
        root_x = self.app.root.winfo_rootx()
        root_y = self.app.root.winfo_rooty()
        if self.app.icon_image is not None:
            self.iconphoto(False, self.app.icon_image)
        self.geometry(f"+{root_x + 40}+{root_y + 40}")

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        notebook = ttk.Notebook(self)
        notebook.grid(row=0, column=0, sticky="nsew")

        general_frame = ttk.Frame(notebook, padding=10)
        general_frame.columnconfigure(1, weight=1)
        notebook.add(general_frame, text="일반")

        ttk.Label(general_frame, text="발음/뜻 표시 시간(초)").grid(row=0, column=0, sticky="w", pady=(0, 5))
        ttk.Entry(general_frame, textvariable=self.show_meaning_var, width=10).grid(
            row=0, column=1, sticky="ew", pady=(0, 5)
        )

        ttk.Label(general_frame, text="다음 단어 표시 시간(초)").grid(row=1, column=0, sticky="w", pady=(0, 5))
        ttk.Entry(general_frame, textvariable=self.next_word_var, width=10).grid(
            row=1, column=1, sticky="ew", pady=(0, 5)
        )

        ttk.Checkbutton(
            general_frame,
            text="항상 위에 표시",
            variable=self.always_on_top_var,
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 10))

        ttk.Button(general_frame, text="설정 저장", command=self._save_settings).grid(
            row=3, column=0, columnspan=2, pady=(0, 5)
        )

        vocab_frame = ttk.Frame(notebook, padding=10)
        vocab_frame.columnconfigure(0, weight=1)
        vocab_frame.rowconfigure(1, weight=1)
        notebook.add(vocab_frame, text="단어")

        ttk.Label(vocab_frame, text="단어 목록").grid(row=0, column=0, sticky="w")

        columns = ("word", "reading", "meaning")
        self.tree = ttk.Treeview(
            vocab_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
            height=10,
        )
        self.tree.heading("word", text="단어")
        self.tree.heading("reading", text="발음")
        self.tree.heading("meaning", text="뜻")
        self.tree.column("word", anchor="w", width=120, stretch=True)
        self.tree.column("reading", anchor="w", width=120, stretch=True)
        self.tree.column("meaning", anchor="w", width=200, stretch=True)

        scrollbar = ttk.Scrollbar(vocab_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.grid(row=1, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns")

        action_frame = ttk.Frame(vocab_frame)
        action_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        ttk.Button(action_frame, text="추가", command=self._add_word).grid(row=0, column=0, padx=5, pady=5)
        ttk.Button(action_frame, text="수정", command=self._edit_word).grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(action_frame, text="삭제", command=self._delete_word).grid(row=0, column=2, padx=5, pady=5)
        ttk.Button(action_frame, text="파일 불러오기", command=self._import_words).grid(
            row=0, column=3, padx=5, pady=5
        )
        ttk.Button(action_frame, text="단어 저장", command=self._save_words).grid(
            row=0, column=4, padx=5, pady=5
        )

        ttk.Button(action_frame, text="JSON 내보내기", command=self._export_json).grid(
            row=1, column=0, columnspan=2, padx=5, pady=5, sticky="w"
        )
        ttk.Button(action_frame, text="CSV 내보내기", command=self._export_csv).grid(
            row=1, column=2, columnspan=2, padx=5, pady=5, sticky="w"
        )

        self._refresh_tree()

    def _on_close(self):
        self.grab_release()
        self.destroy()
        self.app.settings_window = None

    def _save_settings(self):
        show_meaning = parse_positive_int(self.show_meaning_var.get(), -1)
        next_word = parse_positive_int(self.next_word_var.get(), -1)

        if show_meaning <= 0 or next_word <= 0:
            messagebox.showerror("입력 오류", "시간 값은 1 이상의 정수여야 합니다.", parent=self)
            return

        self.app.update_config(show_meaning, next_word, self.always_on_top_var.get())
        messagebox.showinfo("완료", "설정이 저장되었습니다.", parent=self)

    def _refresh_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for index, entry in enumerate(self.words_data):
            self.tree.insert("", "end", iid=str(index), values=(entry["word"], entry["reading"], entry["meaning"]))

    def _get_selected_index(self):
        selection = self.tree.selection()
        if not selection:
            return None
        try:
            return int(selection[0])
        except (ValueError, IndexError):
            return None

    def _open_word_editor(self, title, initial=None):
        dialog = WordEditorDialog(self, title, initial)
        self.wait_window(dialog)
        return dialog.result

    def _add_word(self):
        result = self._open_word_editor("단어 추가")
        if result is None:
            return
        self.words_data.append(result)
        self._refresh_tree()
        self.tree.selection_set(str(len(self.words_data) - 1))

    def _edit_word(self):
        index = self._get_selected_index()
        if index is None:
            messagebox.showwarning("선택 필요", "수정할 단어를 선택하세요.", parent=self)
            return
        current = self.words_data[index]
        result = self._open_word_editor("단어 수정", current)
        if result is None:
            return
        self.words_data[index] = result
        self._refresh_tree()
        self.tree.selection_set(str(index))

    def _delete_word(self):
        index = self._get_selected_index()
        if index is None:
            messagebox.showwarning("선택 필요", "삭제할 단어를 선택하세요.", parent=self)
            return
        confirm = messagebox.askyesno("삭제 확인", "선택한 단어를 삭제하시겠습니까?", parent=self)
        if not confirm:
            return
        del self.words_data[index]
        self._refresh_tree()

    def _save_words(self):
        cleaned = []
        for entry in self.words_data:
            word = entry["word"].strip()
            reading = entry["reading"].strip()
            meaning = entry["meaning"].strip()
            if not (word and reading and meaning):
                continue
            cleaned.append({"word": word, "reading": reading, "meaning": meaning})

        if not cleaned:
            messagebox.showerror("저장 오류", "단어 목록에 최소 한 개의 항목이 필요합니다.", parent=self)
            return

        self.words_data = cleaned
        self._refresh_tree()
        self.app.save_words(self.words_data)
        messagebox.showinfo("완료", "단어 목록이 저장되었습니다.", parent=self)

    def _import_words(self):
        path_str = filedialog.askopenfilename(
            parent=self,
            title="단어 파일 불러오기",
            filetypes=[
                ("지원되는 파일", "*.json *.csv"),
                ("JSON 파일", "*.json"),
                ("CSV 파일", "*.csv"),
                ("모든 파일", "*.*"),
            ],
        )
        if not path_str:
            return

        path = Path(path_str)
        try:
            if path.suffix.lower() == ".csv":
                imported = load_words_from_csv(path)
            else:
                imported = load_words(path)
        except (FileNotFoundError, ValueError) as exc:
            messagebox.showerror("불러오기 실패", str(exc), parent=self)
            return
        except OSError as exc:
            messagebox.showerror("불러오기 실패", f"파일을 열 수 없습니다:\n{exc}", parent=self)
            return

        previous = [dict(item) for item in self.words_data]
        self.words_data = [dict(item) for item in imported]
        self._refresh_tree()

        try:
            self.app.save_words(self.words_data)
        except OSError as exc:
            self.words_data = previous
            self._refresh_tree()
            self.app.set_words(previous)
            messagebox.showerror("저장 실패", f"단어 목록을 저장할 수 없습니다:\n{exc}", parent=self)
            return

        messagebox.showinfo("불러오기", "단어 파일을 불러와 저장했습니다.", parent=self)

    def _export_json(self):
        if not self.words_data:
            messagebox.showwarning("내보내기", "내보낼 단어가 없습니다.", parent=self)
            return
        path = filedialog.asksaveasfilename(
            parent=self,
            title="JSON 내보내기",
            defaultextension=".json",
            filetypes=[("JSON 파일", "*.json"), ("모든 파일", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as json_file:
                json.dump(self.words_data, json_file, ensure_ascii=False, indent=2)
        except OSError as exc:
            messagebox.showerror("내보내기 실패", f"파일을 저장할 수 없습니다:\n{exc}", parent=self)
            return
        messagebox.showinfo("내보내기", "JSON 파일로 내보내기 완료", parent=self)

    def _export_csv(self):
        if not self.words_data:
            messagebox.showwarning("내보내기", "내보낼 단어가 없습니다.", parent=self)
            return
        path = filedialog.asksaveasfilename(
            parent=self,
            title="CSV 내보내기",
            defaultextension=".csv",
            filetypes=[("CSV 파일", "*.csv"), ("모든 파일", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="") as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow(["word", "reading", "meaning"])
                for entry in self.words_data:
                    writer.writerow([entry["word"], entry["reading"], entry["meaning"]])
        except OSError as exc:
            messagebox.showerror("내보내기 실패", f"파일을 저장할 수 없습니다:\n{exc}", parent=self)
            return
        messagebox.showinfo("내보내기", "CSV 파일로 내보내기 완료", parent=self)


class WordEditorDialog(tk.Toplevel):
    def __init__(self, parent: tk.Toplevel, title: str, initial=None):
        super().__init__(parent)
        self.result = None
        self.title(title)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)

        word_value = ""
        reading_value = ""
        meaning_value = ""
        if isinstance(initial, dict):
            word_value = initial.get("word", "")
            reading_value = initial.get("reading", "")
            meaning_value = initial.get("meaning", "")

        self.word_var = tk.StringVar(value=word_value)
        self.reading_var = tk.StringVar(value=reading_value)
        self.meaning_var = tk.StringVar(value=meaning_value)

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.focus()
        self.update_idletasks()
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        self.geometry(f"+{parent_x + 60}+{parent_y + 60}")

    def _build_ui(self):
        padding = {"padx": 10, "pady": 5}

        ttk.Label(self, text="단어").grid(row=0, column=0, sticky="w", **padding)
        ttk.Entry(self, textvariable=self.word_var, width=25).grid(
            row=0, column=1, sticky="ew", **padding
        )

        ttk.Label(self, text="발음").grid(row=1, column=0, sticky="w", **padding)
        ttk.Entry(self, textvariable=self.reading_var, width=25).grid(
            row=1, column=1, sticky="ew", **padding
        )

        ttk.Label(self, text="뜻").grid(row=2, column=0, sticky="w", **padding)
        ttk.Entry(self, textvariable=self.meaning_var, width=25).grid(
            row=2, column=1, sticky="ew", **padding
        )

        button_frame = ttk.Frame(self)
        button_frame.grid(row=3, column=0, columnspan=2, pady=(10, 10))
        ttk.Button(button_frame, text="확인", command=self._on_confirm).grid(
            row=0, column=0, padx=5
        )
        ttk.Button(button_frame, text="취소", command=self._on_cancel).grid(
            row=0, column=1, padx=5
        )

    def _on_confirm(self):
        word = self.word_var.get().strip()
        reading = self.reading_var.get().strip()
        meaning = self.meaning_var.get().strip()
        if not (word and reading and meaning):
            messagebox.showerror("입력 오류", "모든 항목을 입력하세요.", parent=self)
            return
        self.result = {"word": word, "reading": reading, "meaning": meaning}
        self._finish()

    def _on_cancel(self):
        self.result = None
        self._finish()

    def _finish(self):
        self.grab_release()
        self.destroy()


class WordCyclerApp:
    def __init__(self, root: tk.Tk, words):
        self.root = root
        self.root.title("JLPT 단어 암기")
        self.root.resizable(True, True)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.icon_image = None
        self._drag_offset = None
        self.config_manager = ConfigManager(CONFIG_PATH)
        self.word_bank = [dict(item) for item in words]
        self.words = []
        self.current_index = 0

        self.word_var = tk.StringVar()
        self.reading_var = tk.StringVar()
        self.meaning_var = tk.StringVar()

        self.settings_window = None

        self.paused = False
        self.current_job = None
        self.job_callback = None
        self.remaining_ms = None
        self.job_end_time = None

        self._set_window_icon()
        self._build_ui()
        self.root.bind("<Configure>", self._on_resize, add="+")
        self.apply_topmost()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.root.update_idletasks()
        self.root.minsize(self.root.winfo_width(), self.root.winfo_height())
        self._update_wraplengths(self.root.winfo_width())

        self.set_words(self.word_bank)

    def _build_ui(self):
        main_frame = ttk.Frame(self.root, padding=15)
        main_frame.grid(row=0, column=0, sticky="nsew")
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(2, weight=1)
        main_frame.rowconfigure(4, weight=1)

        self.word_label = ttk.Label(
            main_frame, textvariable=self.word_var, font=("Helvetica", 20, "bold")
        )
        self.word_label.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        ttk.Label(main_frame, text="발음", font=("Helvetica", 10)).grid(
            row=1, column=0, sticky="w"
        )
        self.reading_label = ttk.Label(
            main_frame,
            textvariable=self.reading_var,
            font=("Helvetica", 16),
            wraplength=260,
        )
        self.reading_label.grid(row=2, column=0, columnspan=2, sticky="ew")

        ttk.Label(main_frame, text="뜻", font=("Helvetica", 10)).grid(row=3, column=0, sticky="w")
        self.meaning_label = ttk.Label(
            main_frame,
            textvariable=self.meaning_var,
            font=("Helvetica", 16),
            wraplength=260,
        )
        self.meaning_label.grid(row=4, column=0, columnspan=2, sticky="ew")

        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=5, column=0, columnspan=2, pady=(15, 0), sticky="ew")
        control_frame.columnconfigure(0, weight=1)
        control_frame.columnconfigure(1, weight=1)

        self.pause_button = ttk.Button(control_frame, text="일시정지", command=self.toggle_pause)
        self.pause_button.grid(row=0, column=0, padx=5)

        self.settings_button = ttk.Button(control_frame, text="⚙️", width=3, command=self.open_settings)
        self.settings_button.grid(row=0, column=1, padx=5)

        self.root.bind("<ButtonPress-1>", self._start_window_move, add="+")
        self.root.bind("<B1-Motion>", self._perform_window_move, add="+")
        self.root.bind("<ButtonRelease-1>", self._stop_window_move, add="+")

    def _on_resize(self, event):
        if event.widget is self.root:
            self._update_wraplengths(event.width)

    def _update_wraplengths(self, width=None):
        if width is None or width <= 1:
            width = self.root.winfo_width()
        if width <= 1:
            return
        padding = 60
        wrap_length = max(width - padding, 160)
        self.reading_label.configure(wraplength=wrap_length)
        self.meaning_label.configure(wraplength=wrap_length)

    def apply_topmost(self):
        self.root.attributes("-topmost", self.config_manager.data["alwaysOnTop"])

    def open_settings(self):
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.focus_set()
            self.settings_window.lift()
            return
        self.settings_window = SettingsWindow(self)

    def toggle_pause(self):
        if self.paused:
            self.resume()
        else:
            self.pause()

    def pause(self):
        if self.paused:
            return
        self.paused = True
        if self.current_job is not None:
            self.root.after_cancel(self.current_job)
            self.current_job = None
            if self.job_end_time is not None:
                now = time.time() * 1000
                remaining = max(0, self.job_end_time - now)
                self.remaining_ms = remaining
                self.job_end_time = None
        self.pause_button.config(text="재생")

    def resume(self):
        if not self.paused:
            return
        self.paused = False
        self.pause_button.config(text="일시정지")
        self._resume_schedule()

    def update_config(self, show_meaning_timer: int, next_word_timer: int, always_on_top: bool):
        self.config_manager.update(show_meaning_timer, next_word_timer, always_on_top)
        self.apply_topmost()
        was_paused = self.paused
        self._clear_job()
        self.display_word()
        if was_paused:
            self.paused = True
            self.pause_button.config(text="재생")

    def save_words(self, words):
        cleaned = [dict(item) for item in words]
        save_words(WORDS_PATH, cleaned)
        self.word_bank = cleaned
        self.set_words(self.word_bank)

    def set_words(self, words):
        self.word_bank = [dict(item) for item in words]
        self.words = list(self.word_bank)
        if self.words:
            random.shuffle(self.words)
        self.current_index = 0
        was_paused = self.paused
        self._clear_job()
        self.display_word()
        if was_paused:
            self.paused = True
            self.pause_button.config(text="재생")

    def get_all_words(self):
        return [dict(item) for item in self.word_bank]

    def display_word(self):
        if not self.words:
            self.word_var.set("단어 없음")
            self.reading_var.set("")
            self.meaning_var.set("")
            return

        entry = self.words[self.current_index]
        self.word_var.set(entry["word"])
        self.reading_var.set("")
        self.meaning_var.set("")
        self._schedule_after(
            self.config_manager.data["showMeaningTimer"] * 1000, self.display_meaning
        )

    def display_meaning(self):
        entry = self.words[self.current_index]
        self.reading_var.set(entry["reading"])
        self.meaning_var.set(entry["meaning"])
        self._schedule_after(
            self.config_manager.data["nextWordTimer"] * 1000, self.advance_word
        )

    def advance_word(self):
        if not self.words:
            return
        self.current_index = (self.current_index + 1) % len(self.words)
        if self.current_index == 0:
            random.shuffle(self.words)
        self.display_word()

    def _schedule_after(self, delay_ms, callback):
        self._clear_job()
        self.job_callback = callback
        self.remaining_ms = delay_ms
        if not self.paused:
            self.job_end_time = time.time() * 1000 + delay_ms
            self.current_job = self.root.after(delay_ms, self._execute_job)
        else:
            self.job_end_time = None

    def _resume_schedule(self):
        if self.job_callback is None or self.remaining_ms is None:
            return
        delay = int(max(0, self.remaining_ms))
        if delay <= 0:
            callback = self.job_callback
            self.job_callback = None
            self.remaining_ms = None
            self.job_end_time = None
            callback()
        else:
            self.job_end_time = time.time() * 1000 + delay
            self.current_job = self.root.after(delay, self._execute_job)

    def _execute_job(self):
        self.current_job = None
        callback = self.job_callback
        self.job_callback = None
        self.remaining_ms = None
        self.job_end_time = None
        if callback:
            callback()

    def _clear_job(self):
        if self.current_job is not None:
            self.root.after_cancel(self.current_job)
        self.current_job = None
        self.job_callback = None
        self.remaining_ms = None
        self.job_end_time = None

    def _start_window_move(self, event):
        widget = event.widget
        if widget in (self.pause_button, self.settings_button):
            return
        if widget.winfo_toplevel() is not self.root:
            return
        self._drag_offset = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def _perform_window_move(self, event):
        if self._drag_offset is None:
            return
        dx, dy = self._drag_offset
        new_x = event.x_root - dx
        new_y = event.y_root - dy
        self.root.geometry(f"+{new_x}+{new_y}")

    def _stop_window_move(self, event):
        self._drag_offset = None

    def _on_close(self):
        self._clear_job()
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window._on_close()
        self.root.destroy()

    def _set_window_icon(self):
        if ICON_ICO_PATH.exists():
            try:
                self.root.iconbitmap(str(ICON_ICO_PATH))
            except Exception:
                pass
        if ICON_PNG_PATH.exists():
            try:
                self.icon_image = tk.PhotoImage(file=str(ICON_PNG_PATH))
                self.root.iconphoto(False, self.icon_image)
            except Exception:
                self.icon_image = None


def main():
    detach_console_window()
    root = tk.Tk()
    try:
        words = load_words(WORDS_PATH)
    except (FileNotFoundError, ValueError) as exc:
        messagebox.showerror("단어 로드 실패", str(exc), parent=root)
        root.destroy()
        return

    WordCyclerApp(root, words)
    root.mainloop()


if __name__ == "__main__":
    main()
