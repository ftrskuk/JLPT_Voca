import json
import random
import time
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

CONFIG_PATH = Path(__file__).with_name("config.json")
WORDS_PATH = Path(__file__).with_name("words.json")

DEFAULT_CONFIG = {
    "showMeaningTimer": 3,
    "nextWordTimer": 5,
    "alwaysOnTop": True,
}


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
        raise FileNotFoundError("words.json 파일을 찾을 수 없습니다.") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("words.json 형식이 올바르지 않습니다.") from exc

    if not isinstance(raw_words, list) or not raw_words:
        raise ValueError("words.json 에는 하나 이상의 단어가 포함된 배열이 있어야 합니다.")

    words = []
    for item in raw_words:
        if not isinstance(item, dict):
            continue
        word = str(item.get("word", "")).strip()
        reading = str(item.get("reading", "")).strip()
        meaning = str(item.get("meaning", "")).strip()
        if word and reading and meaning:
            words.append({"word": word, "reading": reading, "meaning": meaning})

    if not words:
        raise ValueError("유효한 단어 항목을 words.json 에서 찾을 수 없습니다.")

    return words


class SettingsWindow(tk.Toplevel):
    def __init__(self, app: "WordCyclerApp"):
        super().__init__(app.root)
        self.app = app
        self.title("설정")
        self.resizable(False, False)
        self.transient(app.root)
        self.grab_set()

        self.show_meaning_var = tk.StringVar(value=str(app.config_manager.data["showMeaningTimer"]))
        self.next_word_var = tk.StringVar(value=str(app.config_manager.data["nextWordTimer"]))
        self.always_on_top_var = tk.BooleanVar(value=app.config_manager.data["alwaysOnTop"])

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.focus()
        self.update_idletasks()
        root_x = self.app.root.winfo_rootx()
        root_y = self.app.root.winfo_rooty()
        self.geometry(f"+{root_x + 40}+{root_y + 40}")

    def _build_ui(self):
        padding = {"padx": 10, "pady": 5}

        ttk.Label(self, text="발음/뜻 표시 시간(초)").grid(row=0, column=0, sticky="w", **padding)
        ttk.Entry(self, textvariable=self.show_meaning_var, width=10).grid(
            row=0, column=1, sticky="e", **padding
        )

        ttk.Label(self, text="다음 단어 표시 시간(초)").grid(row=1, column=0, sticky="w", **padding)
        ttk.Entry(self, textvariable=self.next_word_var, width=10).grid(
            row=1, column=1, sticky="e", **padding
        )

        ttk.Checkbutton(self, text="항상 위에 표시", variable=self.always_on_top_var).grid(
            row=2, column=0, columnspan=2, sticky="w", **padding
        )

        button_frame = ttk.Frame(self)
        button_frame.grid(row=3, column=0, columnspan=2, pady=(10, 10))
        ttk.Button(button_frame, text="저장", command=self._save).grid(row=0, column=0, padx=5)

    def _on_close(self):
        self.grab_release()
        self.destroy()
        self.app.settings_window = None

    def _save(self):
        show_meaning = parse_positive_int(self.show_meaning_var.get(), -1)
        next_word = parse_positive_int(self.next_word_var.get(), -1)

        if show_meaning <= 0 or next_word <= 0:
            messagebox.showerror("입력 오류", "시간 값은 1 이상의 정수여야 합니다.", parent=self)
            return

        self.app.update_config(show_meaning, next_word, self.always_on_top_var.get())
        self._on_close()


class WordCyclerApp:
    def __init__(self, root: tk.Tk, words):
        self.root = root
        self.root.title("JLPT 단어 암기")
        self.root.resizable(False, False)

        self.config_manager = ConfigManager(CONFIG_PATH)
        self.words = list(words)
        random.shuffle(self.words)
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

        self._build_ui()
        self.apply_topmost()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.display_word()

    def _build_ui(self):
        main_frame = ttk.Frame(self.root, padding=15)
        main_frame.grid(row=0, column=0)
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)

        ttk.Label(main_frame, textvariable=self.word_var, font=("Helvetica", 20, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10)
        )

        ttk.Label(main_frame, text="발음", font=("Helvetica", 10)).grid(
            row=1, column=0, sticky="w"
        )
        ttk.Label(
            main_frame,
            textvariable=self.reading_var,
            font=("Helvetica", 16),
            wraplength=260,
        ).grid(
            row=2, column=0, columnspan=2, sticky="w"
        )

        ttk.Label(main_frame, text="뜻", font=("Helvetica", 10)).grid(row=3, column=0, sticky="w")
        ttk.Label(
            main_frame,
            textvariable=self.meaning_var,
            font=("Helvetica", 16),
            wraplength=260,
        ).grid(
            row=4, column=0, columnspan=2, sticky="w"
        )

        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=5, column=0, columnspan=2, pady=(15, 0))

        self.pause_button = ttk.Button(control_frame, text="일시정지", command=self.toggle_pause)
        self.pause_button.grid(row=0, column=0, padx=5)

        self.settings_button = ttk.Button(control_frame, text="⚙️", width=3, command=self.open_settings)
        self.settings_button.grid(row=0, column=1, padx=5)

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

    def _on_close(self):
        self._clear_job()
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window._on_close()
        self.root.destroy()


def main():
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
