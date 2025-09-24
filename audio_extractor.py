import wx
import pathlib
import subprocess
import threading
from concurrent.futures import ProcessPoolExecutor, as_completed, CancelledError
import os
import ctypes

# 定义视频文件扩展名
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.ts', '.mpg', '.mpeg'}


# --- 自定义彩色按钮 ---
class ColorButton(wx.Button):
    def __init__(self, parent, id=wx.ID_ANY, label="", pos=wx.DefaultPosition,
                 size=wx.DefaultSize, style=0, validator=wx.DefaultValidator,
                 name="button", bg_color=None, fg_color=None):
        super().__init__(parent, id, label, pos, size, style, validator, name)
        if bg_color:
            self.SetBackgroundColour(bg_color)
        if fg_color:
            self.SetForegroundColour(fg_color)


# --- 文件拖曳目标类 ---
class FileDropTarget(wx.FileDropTarget):
    def __init__(self, text_ctrl):
        # wx.FileDropTarget.__init__(self)
        super().__init__()
        self.text_ctrl = text_ctrl

    def OnDropFiles(self, x, y, filenames):
        if filenames:
            self.text_ctrl.SetValue(filenames[0])
        return True


# --- 主窗口框架 ---
class MainFrame(wx.Frame):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)

        self.executor = None
        self.futures = []
        self.is_running = False
        self.stop_event = threading.Event()

        pnl = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # --- 输入参数部分 ---
        h1_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.txt_input_path = self.create_path_row(pnl, h1_sizer, "输入路径:")
        main_sizer.Add(h1_sizer, 0, wx.EXPAND | wx.ALL, 5)
        h2_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.txt_output_path = self.create_path_row(pnl, h2_sizer, "输出路径:")
        main_sizer.Add(h2_sizer, 0, wx.EXPAND | wx.ALL, 5)

        h3_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.chk_recursive = wx.CheckBox(pnl, label="扫描子文件夹")
        self.chk_recursive.SetValue(True)
        h3_sizer.Add(wx.StaticText(pnl, label=""), 0, wx.RIGHT, 5)
        h3_sizer.Add(self.chk_recursive, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        h3_sizer.Add(wx.StaticText(pnl, label=""), 0, wx.ALL, 5)

        lbl_processes = wx.StaticText(pnl, label="进程数:")
        cpu_count = os.cpu_count() or 4
        self.spin_processes = wx.SpinCtrl(pnl, value=str(cpu_count), min=1, max=cpu_count)
        h3_sizer.Add(lbl_processes, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        h3_sizer.Add(self.spin_processes, 0, wx.ALL, 5)

        # --- 操作按钮部分 ---
        self.btn_start = ColorButton(pnl, label="开始提取", bg_color=(0, 123, 255), fg_color=wx.WHITE)
        self.btn_stop = ColorButton(pnl, label="停止", bg_color=(250, 230, 0), fg_color=wx.BLACK)
        # self.btn_stop = ColorButton(pnl, label="停止")
        self.btn_stop.Disable()
        h3_sizer.Add((50,-1))
        h3_sizer.Add(self.btn_start, 2, wx.EXPAND | wx.ALL, 5)
        h3_sizer.Add(self.btn_stop, 1, wx.EXPAND | wx.ALL, 5)

        main_sizer.Add(h3_sizer, 0, wx.EXPAND | wx.ALL, 5)

        # --- 日志输出部分 ---
        log_box = wx.StaticBox(pnl, label="日志")
        log_sizer = wx.StaticBoxSizer(log_box, wx.VERTICAL)
        self.log_ctrl = wx.TextCtrl(pnl, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
        log_sizer.Add(self.log_ctrl, 1, wx.EXPAND | wx.LEFT, 5)
        main_sizer.Add(log_sizer, 1, wx.EXPAND | wx.TOP | wx.RIGHT, 10)

        # --- 进度条 + 文字 ---
        h4_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.progress_bar = wx.Gauge(pnl, range=100, style=wx.GA_HORIZONTAL | wx.GA_SMOOTH)
        h4_sizer.Add(self.progress_bar, 1, wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)
        # 创建标签并设置最小宽度
        self.process_text = wx.StaticText(pnl, label="进度：-")
        self.process_text.SetMinSize((100, -1))
        h4_sizer.Add(self.process_text, 0, wx.LEFT, 10)
        main_sizer.Add(h4_sizer, 0, wx.EXPAND | wx.ALL, 5)


        pnl.SetSizer(main_sizer)

        # --- 绑定事件 ---
        self.Bind(wx.EVT_BUTTON, self.on_start, self.btn_start)
        self.Bind(wx.EVT_BUTTON, self.on_stop, self.btn_stop)
        self.Bind(wx.EVT_CLOSE, self.on_close)

        self.SetTitle("FFmpeg 音频提取工具")
        self.SetSize((700, 650))
        self.Centre()

    def create_path_row(self, parent, sizer, label_text):
        lbl = wx.StaticText(parent, label=label_text)
        txt_ctrl = wx.TextCtrl(parent)
        btn_browse = wx.Button(parent, label="浏览...")
        drop_target = FileDropTarget(txt_ctrl)
        txt_ctrl.SetDropTarget(drop_target)
        sizer.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        sizer.Add(txt_ctrl, 1, wx.ALL, 5)
        sizer.Add(btn_browse, 0, wx.ALL, 5)
        btn_browse.Bind(wx.EVT_BUTTON, lambda evt, tc=txt_ctrl: self.on_browse(evt, tc))
        return txt_ctrl

    def on_browse(self, event, text_ctrl):
        dlg = wx.DirDialog(self, "请选择一个文件夹", style=wx.DD_DEFAULT_STYLE)
        if dlg.ShowModal() == wx.ID_OK:
            text_ctrl.SetValue(dlg.GetPath())
        dlg.Destroy()

    def log(self, message, color):
        def _log():
            self.log_ctrl.SetDefaultStyle(wx.TextAttr(color))
            self.log_ctrl.AppendText(message + "\n")
            self.log_ctrl.SetDefaultStyle(wx.TextAttr(wx.BLACK))

        wx.CallAfter(_log)

    def update_progress(self, value, range_val=None):
        """更新进度条"""

        def _update():
            if range_val is not None and self.progress_bar.GetRange() != range_val:
                self.progress_bar.SetRange(range_val)
            self.progress_bar.SetValue(value)

        wx.CallAfter(_update)

    def on_start(self, event):
        input_path_str = self.txt_input_path.GetValue()
        output_path_str = self.txt_output_path.GetValue()

        if not input_path_str:
            wx.MessageBox("输入路径不能为空！", "错误", wx.OK | wx.ICON_ERROR)
            return
        input_path = pathlib.Path(input_path_str)
        if not input_path.is_dir():
            wx.MessageBox("输入路径不是一个有效的文件夹！", "错误", wx.OK | wx.ICON_ERROR)
            return

        if output_path_str:
            output_path = pathlib.Path(output_path_str)
            output_path.mkdir(parents=True, exist_ok=True)
        else:
            output_path = input_path
            self.txt_output_path.SetValue(input_path_str)

        self.log_ctrl.Clear()
        self.update_progress(0)
        self.toggle_controls(False)
        self.is_running = True
        self.stop_event.clear()

        threading.Thread(target=self.process_files,
                         args=(input_path, output_path, self.chk_recursive.GetValue(), self.spin_processes.GetValue()),
                         daemon=True).start()

    def on_stop(self, event):
        self.log("正在发送停止信号，请稍候...", "orange")
        self.stop_event.set()
        self.btn_stop.Disable()

    def toggle_controls(self, enable):
        self.btn_start.Enable(enable)
        self.btn_stop.Enable(not enable)
        # 停止按钮只有在运行时才可用
        if enable:
            self.btn_stop.Disable()
        self.txt_input_path.Enable(enable)
        self.txt_output_path.Enable(enable)
        self.chk_recursive.Enable(enable)
        self.spin_processes.Enable(enable)

    def find_video_files(self, input_path, recursive):
        self.log(f"开始在 '{input_path}' 中扫描视频文件...", wx.BLUE)

        pattern = '**/*' if recursive else '*'
        video_files = [f for f in input_path.glob(pattern) if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS]

        self.log(f"扫描完成，共找到 {len(video_files)} 个视频文件。", wx.BLUE)
        return video_files

    def process_files(self, input_path, output_path, recursive, max_workers):
        video_files = self.find_video_files(input_path, recursive)
        if not video_files:
            self.process_text.SetLabelText("进度: 0/0")
            wx.CallAfter(self.toggle_controls, True)
            return

        total_files = len(video_files)
        processed_count = 0
        success_count = 0

        # 初始化进度条范围
        self.update_progress(0, total_files)

        self.executor = ProcessPoolExecutor(max_workers=max_workers)
        self.futures = {self.executor.submit(extract_audio, file, output_path): file for file in video_files}

        for future in as_completed(self.futures):
            if self.stop_event.is_set():
                for f in self.futures:
                    if not f.done():
                        f.cancel()
                break

            processed_count += 1
            progress_str = f"{processed_count}/{total_files}"
            self.process_text.SetLabelText(f"进度: {progress_str}")
            self.update_progress(processed_count)

            try:
                result, message = future.result()
                if result:
                    success_count += 1
                    self.log(message, "#007400")
                else:
                    self.log(message, "red")
            except CancelledError:
                original_file = self.futures[future]
                self.log(f"任务 {original_file.name} 已被取消。", "orange")
            except Exception as e:
                original_file = self.futures[future]
                self.log(f"处理文件 {original_file.name} 时发生意外错误: {e}", "red")

        self.executor.shutdown(wait=True, cancel_futures=True)

        final_status = "任务被用户手动停止" if self.stop_event.is_set() else "所有任务处理完成"
        self.log(f"{final_status}。 成功: {success_count}, 失败/取消: {total_files - success_count}", wx.BLUE)

        self.is_running = False
        self.stop_event.clear()
        wx.CallAfter(self.toggle_controls, True)

    def on_close(self, event):
        if self.is_running:
            dlg = wx.MessageDialog(self, "任务正在运行，确定要退出吗？", "警告", wx.YES_NO | wx.ICON_QUESTION)
            if dlg.ShowModal() == wx.ID_YES:
                self.stop_event.set()
                self.Destroy()
            else:
                dlg.Destroy()
        else:
            self.Destroy()


def extract_audio(video_file, output_path):
    try:
        output_filename = video_file.stem + ".mka"
        output_file_path = output_path / output_filename

        command = ['ffmpeg', '-i', str(video_file), '-vn', '-c:a:0', 'copy', '-y', '-hide_banner', '-loglevel',
                   'error', str(output_file_path)]

        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            startupinfo=startupinfo
        )

        if process.returncode == 0:
            return (True, f"✔ 成功提取: '{output_filename}'")
        else:
            error_message = process.stderr.strip()
            return (False, f"✘ 失败: '{video_file.name}'. 原因: {error_message}")

    except Exception as e:
        return (False, f"✘ 异常: 处理 '{video_file.name}' 时发生错误. 原因: {e}")


if __name__ == '__main__':
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    app = wx.App(False)
    frame = MainFrame(None)
    frame.Show()
    app.MainLoop()
