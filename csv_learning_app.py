import csv
import os
import sys
import time
import subprocess
import shutil
import datetime
import tkinter as tk
from tkinter import filedialog, messagebox
import tkinter.font as tkfont
import difflib
import re
import json
import threading
import customtkinter as ctk

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# 文本测宽用的字体对象缓存，避免每次自适应都新建 tkfont
_MEASURE_CACHE = {}


def strip_parentheses(s, assistant=None):
    if not s:
        return s
    if assistant is not None and not getattr(assistant, 'clean_parentheses', True):
        return str(s).strip()
    s = str(s)
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r'（[^（）]*）', '', s)
        s = re.sub(r'\([^()]*\)', '', s)
        s = re.sub(r'【[^【】]*】', '', s)
        s = re.sub(r'\[[^\[\]]*\]', '', s)
        s = re.sub(r'\{[^{}]*\}', '', s)
        s = re.sub(r'<[^<>]*>', '', s)
    return s.strip()


def clean_answer_string(s, assistant=None):
    if not s:
        return s
    if assistant is not None and not getattr(assistant, 'clean_parentheses', True):
        parts = split_answers(s)
        return ';'.join(p.strip() for p in parts) if parts else str(s).strip()
    parts = split_answers(s)
    cleaned_parts = []
    for p in parts:
        cp = strip_parentheses(p, assistant).strip()
        if cp:
            cleaned_parts.append(cp)
    return ';'.join(cleaned_parts) if cleaned_parts else str(s).strip()


def split_answers(s):
    if not s:
        return []
    s = str(s).strip()
    s = s.replace('；', ';').replace('，', ';').replace(',', ';')
    return [a.strip() for a in s.split(';') if a.strip()]
try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False
try:
    import dashscope
    HAS_DASHSCOPE = True
except ImportError:
    HAS_DASHSCOPE = False
try:
    from zhipuai import ZhipuAI
    HAS_ZHIPU = True
except ImportError:
    HAS_ZHIPU = False
try:
    import ollama
    HAS_OLLAMA = True
except ImportError:
    HAS_OLLAMA = False
import urllib.request
import urllib.error


class OllamaAILearningAssistant:
    def __init__(self):
        self.api_key = None
        self.ai_provider = "ollama"
        self.model = ""
        self.use_ai = True
        self.clean_parentheses = True
        self.ollama_base_url = "http://localhost:11434"
        self.load_config()

    def load_config(self):
        config_file = "ai_config.json"
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.api_key = config.get('api_key')
                    self.ai_provider = config.get('ai_provider', 'ollama')
                    self.model = config.get('model', '')
                    self.use_ai = config.get('use_ai', True)
                    self.clean_parentheses = config.get('clean_parentheses', True)
                    self.ollama_base_url = config.get('ollama_base_url', 'http://localhost:11434')
            except:
                pass

    def save_config(self):
        config = {
            'api_key': self.api_key,
            'ai_provider': self.ai_provider,
            'model': self.model,
            'use_ai': self.use_ai,
            'clean_parentheses': self.clean_parentheses,
            'ollama_base_url': self.ollama_base_url
        }
        with open('ai_config.json', 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    def set_api_key(self, api_key):
        self.api_key = api_key
        self.save_config()

    def set_ai_provider(self, provider):
        self.ai_provider = provider
        self.save_config()

    def set_model(self, model):
        self.model = model
        self.save_config()

    def set_use_ai(self, use_ai):
        self.use_ai = use_ai
        self.save_config()

    def set_clean_parentheses(self, clean_parentheses):
        self.clean_parentheses = clean_parentheses
        self.save_config()

    def set_ollama_base_url(self, url):
        self.ollama_base_url = url
        self.save_config()

    def check_ollama_running(self, auto_start=True):
        if self._check_ollama_http():
            return True
        if auto_start:
            started = self.start_ollama()
            if started:
                for _ in range(30):
                    time.sleep(1)
                    if self._check_ollama_http():
                        return True
        return False

    def _check_ollama_http(self):
        try:
            url = f"{self.ollama_base_url}/api/tags"
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=3) as response:
                return True
        except:
            return False

    def find_ollama_executable(self):
        candidates = []
        ollama_path = os.environ.get('OLLAMA_PATH', '').strip()
        if ollama_path:
            candidates.append(os.path.expandvars(ollama_path))
        try:
            found = shutil.which('ollama')
            if found:
                candidates.append(found)
        except Exception:
            pass
        if sys.platform == 'win32':
            candidates.append(r"C:\Program Files\Ollama\ollama.exe")
            candidates.append(os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"))
            candidates.append(os.path.expandvars(r"%LOCALAPPDATA%\Ollama\ollama.exe"))
            candidates.append(os.path.expandvars(r"%APPDATA%\Ollama\ollama.exe"))
            candidates.append(os.path.expandvars(r"%ProgramData%\Ollama\ollama.exe"))
            try:
                la = os.environ.get('LOCALAPPDATA', '')
                if la:
                    for root, dirs, files in os.walk(la):
                        if 'ollama.exe' in files:
                            candidates.append(os.path.join(root, 'ollama.exe'))
                            break
            except Exception:
                pass
        elif sys.platform == 'darwin':
            candidates.append("/Applications/Ollama.app/Contents/Resources/bin/ollama")
            candidates.append("/usr/local/bin/ollama")
        else:
            candidates.append("/usr/local/bin/ollama")
            candidates.append("/usr/bin/ollama")
            candidates.append("/snap/bin/ollama")
        for c in candidates:
            c = c.strip()
            if c and os.path.isfile(c):
                return c
        return None

    def start_ollama(self):
        exe = self.find_ollama_executable()
        if not exe:
            return False
        try:
            env = os.environ.copy()
            env['OLLAMA_HOST'] = self.ollama_base_url
            if sys.platform == 'win32':
                DETACHED_PROCESS = 0x00000008
                CREATE_NO_WINDOW = 0x08000000
                subprocess.Popen(
                    [exe, 'serve'],
                    creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
                    env=env,
                    close_fds=True
                )
            else:
                subprocess.Popen(
                    [exe, 'serve'],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                    env=env
                )
            return True
        except Exception as e:
            print(f"启动 Ollama 失败: {e}")
            return False

    def get_ollama_models(self, silent=False):
        models = []
        try:
            if HAS_OLLAMA:
                model_list = ollama.list()
                if hasattr(model_list, 'models'):
                    models = [m['model'] for m in model_list.models]
                elif isinstance(model_list, dict) and 'models' in model_list:
                    models = [m['model'] for m in model_list['models']]
            else:
                models = self._get_models_http(silent=silent)
        except Exception as e:
            if not silent:
                print(f"获取Ollama模型失败: {e}")
        
        return models

    def _get_models_http(self, silent=False):
        try:
            url = f"{self.ollama_base_url}/api/tags"
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
                if 'models' in data:
                    return [m['model'] for m in data['models']]
        except Exception as e:
            if not silent:
                print(f"HTTP获取模型失败: {e}")
        return []

    def get_available_providers(self):
        providers = {
            'ollama': {'name': '🦙 Ollama (本地)', 'models': [], 'desc': '完全本地，免费无限用'},
            'local': {'name': '本地算法', 'models': [], 'desc': '无需网络，快速响应'},
        }

        if HAS_OPENAI:
            providers['openai'] = {
                'name': 'OpenAI (国外)',
                'models': ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-4', 'gpt-3.5-turbo'],
                'desc': '需要科学上网'
            }

        if HAS_DASHSCOPE:
            providers['qwen'] = {
                'name': '🇨🇳 通义千问 (阿里)',
                'models': ['qwen-turbo', 'qwen-plus', 'qwen-max', 'qwen-max-longcontext'],
                'desc': '阿里云大模型'
            }

        if HAS_ZHIPU:
            providers['zhipu'] = {
                'name': '🇨🇳 智谱GLM',
                'models': ['glm-4', 'glm-4-flash', 'glm-4-plus'],
                'desc': '清华智谱AI'
            }

        providers['baidu'] = {
            'name': '🇨🇳 文心一言 (百度)',
            'models': ['ernie-bot-4', 'ernie-bot', 'ernie-bot-turbo'],
            'desc': '百度文心大模型'
        }

        ollama_models = self.get_ollama_models(silent=True)
        if ollama_models:
            providers['ollama']['models'] = sorted(ollama_models)

        return providers

    def ai_judge_with_ai(self, user_answer, correct_answer, col1, col2):
        if not self.use_ai:
            return None

        try:
            if self.ai_provider == 'ollama':
                return self._call_ollama(user_answer, correct_answer, col1, col2)
            elif self.ai_provider == 'openai' and HAS_OPENAI and self.api_key:
                return self._call_openai(user_answer, correct_answer, col1, col2)
            elif self.ai_provider == 'qwen' and HAS_DASHSCOPE and self.api_key:
                return self._call_qwen(user_answer, correct_answer, col1, col2)
            elif self.ai_provider == 'zhipu' and HAS_ZHIPU and self.api_key:
                return self._call_zhipu(user_answer, correct_answer, col1, col2)
            elif self.ai_provider == 'baidu' and self.api_key:
                return self._call_baidu(user_answer, correct_answer, col1, col2)

        except Exception as e:
            import difflib as _difflib
            user_clean = re.sub(r'\s+', '', str(user_answer).lower())
            possible = split_answers(correct_answer)
            best_sim = 0.0
            best_ans = ''
            for a in possible:
                ac = re.sub(r'\s+', '', strip_parentheses(a, self).lower())
                if user_clean == ac:
                    best_sim = 1.0
                    best_ans = a
                    break
                sim = _difflib.SequenceMatcher(None, user_clean, ac).ratio()
                if sim > best_sim:
                    best_sim = sim
                    best_ans = a
            is_correct = best_sim >= 0.85
            clean_best = strip_parentheses(best_ans, self)
            return {
                'is_correct': is_correct,
                'confidence': best_sim,
                'analysis': f'AI异常，本地判定{"✅对" if is_correct else "❌错"} (相似度{best_sim:.0%})',
                'suggestions': f'标准答案：{clean_best}' if not is_correct else '',
                'similarity_score': best_sim
            }

    def _get_prompt(self, user_answer, correct_answer, col1, col2):
        clean_correct = clean_answer_string(correct_answer, self)
        prompt = f'''判断词汇默写对错。
正确只返回：正确，正确答案是：XXX
错误只返回：错误，正确答案是：XXX

例子：
标准: 苹果 | 答: 苹果 → 正确，正确答案是：苹果
标准: 跑;奔跑 | 答: 奔跑 → 正确，正确答案是：跑;奔跑
标准: 高兴的 | 答: 高兴 → 错误，正确答案是：高兴的
标准: 吃 | 答: 食物 → 错误，正确答案是：吃
标准: 橙子;柑橘 | 答: 橘子 → 正确，正确答案是：橙子;柑橘

题目：{col1} ({col2})
标准：{clean_correct}
学生：{user_answer}
返回：'''
        return prompt

    def _parse_result(self, result_text):
        try:
            cleaned = result_text.strip()

            import re

            is_correct = False
            analysis = ''

            if cleaned.startswith('正确') or cleaned == '正确':
                is_correct = True
                analysis = '✅ AI判定正确'
            elif cleaned.startswith('错误') or '错误' in cleaned[:10]:
                is_correct = False
                m = re.search(r'正确答案[是为：:]*[：:\s]*([^\n。，]+)', cleaned)
                if m:
                    analysis = f'正确答案：{m.group(1).strip()}'
                else:
                    analysis = cleaned[:50]
            else:
                json_match = re.search(r'\{[^{}]*"r"[^{}]*\}', cleaned, re.DOTALL)
                if not json_match:
                    json_match = re.search(r'\{[^{}]*"is_correct"[^{}]*\}', cleaned, re.DOTALL)
                if json_match:
                    cleaned_json = json_match.group(0)
                    raw = json.loads(cleaned_json)
                    if 'r' in raw:
                        is_correct = bool(raw['r'] == 1 or raw['r'] == True)
                        analysis = raw.get('e','')
                    elif 'is_correct' in raw:
                        is_correct = bool(raw['is_correct'])
                        analysis = raw.get('analysis','')
                else:
                    if '正确' in cleaned and '错误' not in cleaned:
                        is_correct = True
                    else:
                        import difflib as _difflib
                        user_answer = getattr(self, '_last_user_answer', '')
                        correct_answer = getattr(self, '_last_correct_answer', '')
                        if user_answer and correct_answer:
                            uc = re.sub(r'\s+', '', str(user_answer).lower())
                            possible = split_answers(correct_answer)
                            best_sim = 0.0
                            for a in possible:
                                ac = re.sub(r'\s+', '', strip_parentheses(a, self).lower())
                                if uc == ac:
                                    best_sim = 1.0
                                    break
                                sim = _difflib.SequenceMatcher(None, uc, ac).ratio()
                                if sim > best_sim:
                                    best_sim = sim
                            is_correct = best_sim >= 0.85
                            analysis = f'相似度{best_sim:.0%}'
                        else:
                            is_correct = False
                            analysis = cleaned[:50]

            rj = {
                'is_correct': is_correct,
                'confidence': 1.0,
                'analysis': analysis,
                'suggestions': '',
                'similarity_score': 0.9 if is_correct else 0.3
            }

            user_answer = getattr(self, '_last_user_answer', '')
            correct_answer = getattr(self, '_last_correct_answer', '')

            if user_answer and correct_answer:
                user_clean = re.sub(r'\s+', '', str(user_answer).lower())
                possible_answers = split_answers(correct_answer)
                for ans in possible_answers:
                    ans_clean = re.sub(r'\s+', '', strip_parentheses(ans, self).lower())
                    if user_clean == ans_clean:
                        rj['is_correct'] = True
                        rj['confidence'] = 1.0
                        rj['similarity_score'] = 1.0
                        rj['analysis'] = '✅ 完全匹配'
                        break

            return rj

        except Exception as e:
            user_answer = getattr(self, '_last_user_answer', '')
            correct_answer = getattr(self, '_last_correct_answer', '')

            if user_answer and correct_answer:
                user_clean = re.sub(r'\s+', '', str(user_answer).lower())
                possible_answers = split_answers(correct_answer)
                for ans in possible_answers:
                    ans_clean = re.sub(r'\s+', '', strip_parentheses(ans, self).lower())
                    if user_clean == ans_clean:
                        return {
                            'is_correct': True,
                            'confidence': 1.0,
                            'analysis': '✅ 正确',
                            'suggestions': '',
                            'similarity_score': 1.0
                        }

            return {
                'is_correct': False,
                'confidence': 0.5,
                'analysis': f'AI返回格式错误: {str(result_text)[:100]}',
                'suggestions': '',
                'similarity_score': 0.5
            }
    def _call_ollama(self, user_answer, correct_answer, col1, col2):
        model = self.model or 'phi3:mini'

        if HAS_OLLAMA:
            response = ollama.chat(
                model=model,
                messages=[
                    {"role": "system", "content": "判断对错。正确只写：正确；错误只写：错误，正确答案是：XXX"},
                    {"role": "user", "content": self._get_prompt(user_answer, correct_answer, col1, col2)}
                ],
                options={
                    'temperature': 0.1,
                    'num_predict': 100
                }
            )

            result_text = response['message']['content'].strip()
            return self._parse_result(result_text)
        else:
            return self._call_ollama_http(user_answer, correct_answer, col1, col2)

    def _call_ollama_http(self, user_answer, correct_answer, col1, col2):
        model = self.model or 'phi3:mini'
        url = f"{self.ollama_base_url}/api/chat"

        data = {
            "model": model,
            "messages": [
                {"role": "system", "content": "判断对错。正确只写：正确；错误只写：错误，正确答案是：XXX"},
                {"role": "user", "content": self._get_prompt(user_answer, correct_answer, col1, col2)}
            ],
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 100
            }
        }

        encoded_data = json.dumps(data).encode('utf-8')
        req = urllib.request.Request(url, data=encoded_data, method='POST')
        req.add_header('Content-Type', 'application/json')

        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            result_text = result.get('message', {}).get('content', '').strip()
            return self._parse_result(result_text)

    def _call_openai(self, user_answer, correct_answer, col1, col2):
        client = openai.OpenAI(api_key=self.api_key)
        
        response = client.chat.completions.create(
            model=self.model or 'gpt-3.5-turbo',
            messages=[
                {"role": "system", "content": "你是一个专业、友好、鼓励性的教育AI助手。"},
                {"role": "user", "content": self._get_prompt(user_answer, correct_answer, col1, col2)}
            ],
            temperature=0.3,
            max_tokens=500
        )
        
        result_text = response.choices[0].message.content.strip()
        return self._parse_result(result_text)

    def _call_qwen(self, user_answer, correct_answer, col1, col2):
        dashscope.api_key = self.api_key
        
        response = dashscope.Generation.call(
            model=self.model or 'qwen-turbo',
            messages=[
                {"role": "system", "content": "你是一个专业、友好、鼓励性的教育AI助手。"},
                {"role": "user", "content": self._get_prompt(user_answer, correct_answer, col1, col2)}
            ],
            temperature=0.3,
            max_tokens=500
        )
        
        if response.status_code == 200:
            result_text = response.output.text.strip()
            return self._parse_result(result_text)
        else:
            raise Exception(f"通义千问API错误: {response.message}")

    def _call_zhipu(self, user_answer, correct_answer, col1, col2):
        client = ZhipuAI(api_key=self.api_key)
        
        response = client.chat.completions.create(
            model=self.model or 'glm-4-flash',
            messages=[
                {"role": "system", "content": "你是一个专业、友好、鼓励性的教育AI助手。"},
                {"role": "user", "content": self._get_prompt(user_answer, correct_answer, col1, col2)}
            ],
            temperature=0.3,
            max_tokens=500
        )
        
        result_text = response.choices[0].message.content.strip()
        return self._parse_result(result_text)

    def _call_baidu(self, user_answer, correct_answer, col1, col2):
        url = "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/completions"
        
        data = {
            "messages": [
                {"role": "system", "content": "你是一个专业、友好、鼓励性的教育AI助手。"},
                {"role": "user", "content": self._get_prompt(user_answer, correct_answer, col1, col2)}
            ],
            "temperature": 0.3,
            "max_output_tokens": 500
        }
        
        encoded_data = json.dumps(data).encode('utf-8')
        req = urllib.request.Request(url, data=encoded_data, method='POST')
        req.add_header('Content-Type', 'application/json')
        
        token_url = f"https://aip.baidubce.com/oauth/2.0/token?grant_type=client_credentials&client_id={self.api_key}"
        
        try:
            with urllib.request.urlopen(token_url) as response:
                token_result = json.loads(response.read().decode())
                access_token = token_result.get('access_token')
                
                full_url = f"{url}?access_token={access_token}"
                req.full_url = full_url
                
                with urllib.request.urlopen(req) as resp:
                    result = json.loads(resp.read().decode())
                    result_text = result.get('result', '').strip()
                    return self._parse_result(result_text)
                    
        except urllib.error.URLError as e:
            raise Exception(f"百度API调用失败: {str(e)}")


class _SimpleTip:
    """极简悬停提示：鼠标移入显示小标签，移出隐藏。

    注意：CTkButton 把 <Enter>/<Leave> 绑在内部的 _canvas 上（不是外层 frame），
    所以要绑到 canvas 才收得到事件。
    """

    def __init__(self, widget, text, delay=350):
        self.widget = widget
        self.text = text
        self.delay = delay
        self._after_id = None
        self._tip_win = None
        self._targets = []
        try:
            canvas = getattr(widget, "_canvas", None)
            if canvas is not None:
                self._targets = [canvas]
                lbl = getattr(widget, "_text_label", None)
                if lbl is not None:
                    self._targets.append(lbl)
            else:
                self._targets = [widget]
            for t in self._targets:
                t.bind("<Enter>", self._schedule, add="+")
                t.bind("<Leave>", self._hide, add="+")
                t.bind("<ButtonPress>", self._hide, add="+")
        except Exception:
            pass

    def _schedule(self, event=None):
        self._cancel()
        self._after_id = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show(self):
        self._after_id = None
        if self._tip_win is not None:
            return
        try:
            x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
            self._tip_win = tk.Toplevel(self.widget)
            self._tip_win.wm_overrideredirect(True)
            self._tip_win.wm_geometry(f"+{x}+{y}")
            lbl = tk.Label(self._tip_win, text=self.text, bg="#2b313b",
                           fg="#cfd6df", padx=6, pady=3,
                           font=("Microsoft YaHei UI", 9))
            lbl.pack()
            self._tip_win.after(2500, self._hide)
        except Exception:
            self._tip_win = None

    def _hide(self, event=None):
        self._cancel()
        if self._tip_win is not None:
            try:
                self._tip_win.destroy()
            except Exception:
                pass
            self._tip_win = None


class _PageStack(ctk.CTkFrame):
    """无标签栏的多页面容器。

    早期版本用 CTkSegmentedButton 做「学习模式 / AI设置」标签栏，但顶栏已经有
    「AI」胶囊、设置页也有「← 学习」返回，标签栏纯属重复且占用纵向空间。
    这里只保留切换逻辑，标签栏彻底去掉。
    """

    def __init__(self, master):
        super().__init__(master, fg_color="#21252b", corner_radius=0)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._page_dict = {}
        self._name_list = []
        self._current_name = ""

    def add(self, name):
        frame = ctk.CTkFrame(self, fg_color="#21252b", corner_radius=0)
        self._page_dict[name] = frame
        self._name_list.append(name)

        if not self._current_name:
            self._current_name = name
            frame.grid(row=0, column=0, sticky="nsew")
        return frame

    def select(self, name):
        """切换到指定页面。"""
        if name not in self._page_dict or name == self._current_name:
            return
        self._page_dict[self._current_name].grid_forget()
        self._current_name = name
        self._page_dict[name].grid(row=0, column=0, sticky="nsew")

    @property
    def current(self):
        return self._current_name

    def tab(self, name):
        return self._page_dict[name]


class CSVLearningApp:
    def __init__(self, root):
        self.root = root
        self.root.title("📚 词汇学习默写工具")
        self.geometry("900x760")
        # 下限：单列布局，窄到 560 也能正常默写
        self.root.minsize(560, 520)

        self.current_csv_data = []
        self.current_index = 0
        self.wrong_answers = []
        self.current_round = 1
        self.total_questions = 0
        self.correct_count = 0
        self.wrong_count = 0
        self.csv_file_path = None
        self.csv_file_paths = []
        self.ai_assistant = OllamaAILearningAssistant()
        self.processing = False
        self.clean_paren_var = None

        self._font_specs = {}
        self._base_w = 1100
        self._base_h = 900
        self._question_size_cache = {}
        self._entry_typing = False

        self.setup_ui()
        self._last_resize_size = (0, 0)
        self._resize_timer = None
        self.root.bind('<Configure>', self._on_window_resize)
        self.root.bind('<Escape>', self._on_global_escape, add='+')
        self.root.bind('<Button-1>', self._on_global_click, add='+')
        self.root.after(100, self._update_all_font_sizes)
        self.root.after(800, self._ensure_ollama_running_async_startup)

    def _on_toggle_clean_paren(self):
        enabled = self.clean_paren_var.get()
        self.ai_assistant.set_clean_parentheses(enabled)
        status = "已开启" if enabled else "已关闭"
        self.ai_result_text.insert(tk.END, f"🧹 括号清理功能 {status}\n")
        self.ai_result_text.see(tk.END)

    def _sync_paren_style_from_state(self, enabled):
        """括号开关只在设置页有一份，这里同步它的配色。"""
        switch = getattr(self, 'paren_check', None)
        if not switch:
            return
        try:
            color = "#2ecc71" if enabled else "#95a5a6"
            switch.configure(button_color=color, button_hover_color=color)
        except Exception:
            pass

    def _update_paren_tooltip(self):
        enabled = self.clean_paren_var.get() if self.clean_paren_var else True
        self._sync_paren_style_from_state(enabled)

    def _sync_paren_ui_from_config(self):
        val = self.ai_assistant.clean_parentheses
        if self.clean_paren_var is not None:
            self.clean_paren_var.set(val)
        self._update_paren_tooltip()
        self._sync_paren_style_from_state(val)

    def geometry(self, size):
        self.root.geometry(size)

    def _on_window_resize(self, event):
        if event.widget is not self.root:
            return
        size = (event.width, event.height)
        if size != self._last_resize_size:
            self._last_resize_size = size
            if self._resize_timer:
                self.root.after_cancel(self._resize_timer)
            self._resize_timer = self.root.after(250, self._on_resize_settled)

    def _on_resize_settled(self):
        self._resize_timer = None
        self._update_all_font_sizes()

    def _register_font(self, attr_name, family, base_size, **kwargs):
        self._font_specs[attr_name] = (family, base_size, kwargs)

    def _ensure_ollama_running_async_startup(self):
        if self.ai_assistant._check_ollama_http():
            self.update_ai_status()
            self._refresh_models_silent()
            return

        def worker():
            started = self.ai_assistant.start_ollama()
            if not started:
                return
            for i in range(30):
                time.sleep(1)
                if self.ai_assistant._check_ollama_http():
                    self.root.after(0, self.update_ai_status)
                    self.root.after(0, self._refresh_models_silent)
                    return

        threading.Thread(target=worker, daemon=True).start()

    def _refresh_models_silent(self):
        """自动拉取模型列表并同步到下拉框，不改动状态标签文字。

        Ollama 自动启动后模型才真正可枚举，启动流程里必须补这一步，
        否则「选择模型」下拉框一直空着/显示旧值，只能手动点刷新。
        """
        try:
            if not hasattr(self, 'model_combo'):
                return
            models = self.ai_assistant.get_ollama_models()
            if not models:
                return
            models = sorted(models)
            self.model_combo.configure(values=models)
            current = self.model_combo.get()
            if current not in models:
                preferred = 'qwen2.5:7b' if 'qwen2.5:7b' in models else models[0]
                self.model_combo.set(preferred)
            self.ai_assistant.get_available_providers()['ollama']['models'] = models
        except Exception:
            pass

    def _ensure_ollama_running_async(self, on_done=None, silent=False):
        if self.ai_assistant._check_ollama_http():
            self.root.after(0, lambda: self._on_ollama_ready(on_done, silent))
            return
        if not silent:
            self.ai_result_text.insert(tk.END, "🦙 Ollama 未运行，正在自动启动...\n")
            self.ai_result_text.see(tk.END)
            try:
                self.ollama_status_label.configure(text="🦙 正在启动 Ollama...", text_color="#f39c12")
            except Exception:
                pass

        def worker():
            started = self.ai_assistant.start_ollama()
            if not started:
                self.root.after(0, lambda: self._on_ollama_failed(on_done, silent))
                return
            for i in range(30):
                time.sleep(1)
                if self.ai_assistant._check_ollama_http():
                    self.root.after(0, lambda: self._on_ollama_ready(on_done, silent))
                    return
                if not silent and (i + 1) % 5 == 0:
                    self.root.after(0, lambda sec=i+1: self.ai_result_text.insert(tk.END, f"  ⏳ 等待 Ollama 就绪 ({sec}s)...\n") or self.ai_result_text.see(tk.END))
            self.root.after(0, lambda: self._on_ollama_failed(on_done, silent))

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def _on_ollama_ready(self, on_done, silent):
        self.update_ai_status()
        if not silent:
            self.ai_result_text.insert(tk.END, "✅ Ollama 已就绪！\n")
            self.ai_result_text.see(tk.END)
        self._refresh_models_silent()
        if on_done:
            try:
                on_done(True)
            except Exception:
                pass

    def _on_ollama_failed(self, on_done, silent):
        self.update_ai_status()
        exe = self.ai_assistant.find_ollama_executable()
        if not silent:
            if exe:
                msg = f"⚠️ 自动启动 Ollama 超时，将使用本地相似度算法\n💡 可手动在终端运行: \"{exe} serve\""
            else:
                msg = "⚠️ 未找到 Ollama 可执行文件\n💡 请从 https://ollama.com 下载安装后重试"
            self.ai_result_text.insert(tk.END, msg + "\n")
            self.ai_result_text.see(tk.END)
            try:
                self.ollama_status_label.configure(text="🦙 Ollama (未连接)", text_color="#e74c3c")
            except Exception:
                pass
        if on_done:
            try:
                on_done(False)
            except Exception:
                pass

    def _window_logical_size(self):
        """返回窗口的逻辑宽高（用户感知尺寸）。

        必须用它而不是 winfo_width()：CTk 的 geometry()/minsize() 都按
        DPI 缩放，150% 缩放下设 720x560 实际拿到 1080x840 物理像素，
        拿物理像素算缩放会把所有字号额外放大 1.5 倍。
        """
        try:
            s = self.root._get_window_scaling()
        except Exception:
            s = 1.0
        if not s or s <= 0:
            s = 1.0
        return (self.root.winfo_width() / s, self.root.winfo_height() / s)

    def _compute_scale(self):
        # 注意：必须用逻辑尺寸。_base_w/_base_h 是逻辑基准（1100x900），
        # 而 winfo_width() 在 150% DPI 下返回物理像素（1650），
        # 混用会让所有字号被额外放大 1.5 倍。
        w, h = self._window_logical_size()
        w = max(w, 100)
        h = max(h, 100)
        scale = min(w / self._base_w, h / self._base_h)
        return max(0.55, min(scale, 2.2))

    @staticmethod
    def _text_px(text, size, bold=False):
        """量出某段文本在给定字号下的像素宽度（按字号缓存测量字体）。"""
        if not text:
            return 0
        key = (size, bold)
        font = _MEASURE_CACHE.get(key)
        if font is None:
            font = tkfont.Font(family="Microsoft YaHei UI", size=size,
                               weight="bold" if bold else "normal")
            _MEASURE_CACHE[key] = font
        return font.measure(text)

    def _update_all_font_sizes(self):
        win_scale = self._compute_scale()
        ui_scale = max(0.7, min(win_scale, 2.0))
        question_attrs = ('col1_value', 'col2_value')
        for attr_name, (family, base_size, kwargs) in self._font_specs.items():
            if attr_name in question_attrs:
                continue
            try:
                widget = getattr(self, attr_name, None)
                if widget is None:
                    continue
                if base_size <= 16:
                    new_size = max(6, int(round(base_size * ui_scale)))
                else:
                    new_size = max(10, int(round(base_size * win_scale)))
                widget.configure(font=ctk.CTkFont(family=family, size=new_size, **kwargs))
                # 胶囊按钮的宽高跟着字号缩放，否则小字配大按钮很怪
                base = getattr(widget, "_pill_base", None)
                if base:
                    w_ratio = new_size / 12.0
                    widget.configure(width=max(28, int(base[0] * w_ratio)),
                                     height=max(20, int(base[1] * w_ratio)))
            except Exception:
                pass
        self._update_question_fonts()

    def setup_ui(self):
        main_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=10, pady=10)

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(0, weight=1)

        pages = _PageStack(main_frame)
        pages.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.pages = pages

        learning_page = pages.add("学习")
        settings_page = pages.add("AI设置")

        self.setup_learning_tab(learning_page)
        self.setup_settings_tab(settings_page)
        self._sync_paren_ui_from_config()
        self.update_ai_status()

    def setup_learning_tab(self, parent):
        """构建唯一的学习界面（不再区分完整模式 / 简洁模式）。

        自上而下：工具条 → 状态行 → 判定卡 → 单词卡 → 正确答案卡
        → 输入行 → AI 判定详情（可折叠）。
        低频操作（进度存取 / 新一轮 / 导出 / 重置）收进「⋯ 更多」浮层。
        """
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        wrap = ctk.CTkFrame(parent, fg_color="#21252b", corner_radius=12,
                             border_width=1, border_color="#33383f")
        wrap.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=8, pady=5)
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(3, weight=1)   # 单词卡吃掉剩余高度
        self.main_wrap = wrap

        # ---- 顶部工具条：文件信息 + 文件 / AI / 更多 三个胶囊 ----
        bar = ctk.CTkFrame(wrap, fg_color="transparent")
        bar.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=14, pady=(10, 0))
        bar.columnconfigure(0, weight=1)

        self.file_label = ctk.CTkLabel(
            bar, text="未选择文件", anchor="w",
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=12),
            text_color="#8b95a3")
        self.file_label.grid(row=0, column=0, sticky=tk.W)

        self.btn_file = self._pill(bar, "文件", self.load_csv, width=48)
        self.btn_file.grid(row=0, column=1, padx=(0, 6))
        self._bind_hint(self.btn_file, "加载 CSV 词汇表")

        self.btn_ai = self._pill(bar, "AI", self._goto_ai_settings, width=44)
        self.btn_ai.grid(row=0, column=2, padx=(0, 6))
        self._bind_hint(self.btn_ai, "打开 AI 设置页")

        self.btn_more = self._pill(bar, "⋯", self._toggle_more_menu, width=34)
        self.btn_more.grid(row=0, column=3)
        self._bind_hint(self.btn_more, "更多操作")

        self._register_font('file_label', 'Microsoft YaHei UI', 12)
        self._register_font('btn_file', 'Microsoft YaHei UI', 12)
        self._register_font('btn_ai', 'Microsoft YaHei UI', 12)
        self._register_font('btn_more', 'Microsoft YaHei UI', 12)

        # ---- 状态行：轮次 / 进度 / 对错 / AI 状态 合并为一行 ----
        self._ai_status_text = "Ollama 未连接"
        self.status_label = ctk.CTkLabel(
            wrap, text="第 1 轮 · 0/0 · 对 0 错 0 · Ollama 未连接", anchor="w",
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=12),
            text_color="#7f8896")
        self.status_label.grid(row=1, column=0, sticky=(tk.W, tk.E), padx=14, pady=(6, 0))
        self._register_font('status_label', 'Microsoft YaHei UI', 12)

        # ---- 判定卡：状态文字 + 查看答案 / 跳过 / 改对 / 改错 ----
        self.verdict_card = ctk.CTkFrame(wrap, fg_color="#2b313b", corner_radius=12)
        self.verdict_card.grid(row=2, column=0, sticky=(tk.W, tk.E), padx=14, pady=(10, 0))

        self.verdict_label = ctk.CTkLabel(
            self.verdict_card, text="等待作答", anchor="w",
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=24),
            text_color="#9aa4b2")
        self.verdict_label.grid(row=0, column=0, sticky=tk.W, padx=14, pady=11)

        verdict_btns = ctk.CTkFrame(self.verdict_card, fg_color="transparent")
        verdict_btns.grid(row=0, column=1, sticky=tk.E, padx=(0, 10), pady=10)

        self.btn_view_answer = self._pill(verdict_btns, "查看答案", self._reveal_answer,
                                          width=68, fg_color="#3a4150")
        self.btn_view_answer.grid(row=0, column=0, padx=(0, 6))

        self.btn_skip = self._pill(verdict_btns, "跳过", self.skip_question,
                                   width=48, fg_color="#3a4150")
        self.btn_skip.grid(row=0, column=1, padx=(0, 6))

        self.btn_mark_correct = self._pill(verdict_btns, "改对", self.mark_as_correct,
                                            width=48, fg_color="#3a4150")
        self.btn_mark_correct.grid(row=0, column=2, padx=(0, 6))

        self.btn_mark_wrong = self._pill(verdict_btns, "改错", self.mark_as_wrong,
                                          width=48, fg_color="#3a4150")
        self.btn_mark_wrong.grid(row=0, column=3)

        self._register_font('verdict_label', 'Microsoft YaHei UI', 24)
        for _attr in ('btn_view_answer', 'btn_skip', 'btn_mark_correct', 'btn_mark_wrong'):
            self._register_font(_attr, 'Microsoft YaHei UI', 12)

        # ---- 单词 + 词性 ----
        self.word_card = ctk.CTkFrame(
            wrap, fg_color="#282e38", corner_radius=12,
            border_width=1, border_color="#39404f")
        self.word_card.grid(row=3, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=14, pady=(10, 0))
        self.word_card.columnconfigure(0, weight=1)
        self.word_card.rowconfigure(0, weight=1)
        self.word_card.bind('<Configure>',
                            lambda e: self._update_question_fonts() if e.widget is self.word_card else None)

        holder = ctk.CTkFrame(self.word_card, fg_color="transparent")
        holder.pack(fill="both", expand=True, padx=14, pady=18)
        holder.columnconfigure(0, weight=1)
        # 上下各留一段弹性空白，让「单词 + 词性」这一组整体垂直居中，
        # 否则词性会被 row weight 顶到卡片底部，和设计稿差很远。
        holder.rowconfigure(0, weight=1)
        holder.rowconfigure(3, weight=1)

        self.col1_value = ctk.CTkLabel(
            holder, text="-", font=ctk.CTkFont(family='Microsoft YaHei UI', size=32, weight="bold"),
            text_color="#7fc4ff", anchor="center", justify="center")
        self.col1_value.grid(row=1, column=0, sticky="ew")

        self.col2_value = ctk.CTkLabel(
            holder, text="-", font=ctk.CTkFont(family='Microsoft YaHei UI', size=18),
            text_color="#f1948a", anchor="center", justify="center")
        self.col2_value.grid(row=2, column=0, sticky="ew", pady=(4, 0))

        # ---- 正确答案卡 ----
        self.answer_card = ctk.CTkFrame(wrap, fg_color="#2b313b", corner_radius=12)
        self.answer_card.grid(row=4, column=0, sticky=(tk.W, tk.E), padx=14, pady=(10, 0))

        ctk.CTkLabel(
            self.answer_card, text="正确答案", anchor="w",
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=12),
            text_color="#7f8896").grid(row=0, column=0, sticky=tk.W, padx=14, pady=(9, 0))

        self.answer_value_label = ctk.CTkLabel(
            self.answer_card, text="· · ·", anchor="w", justify="left",
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=16),
            text_color="#f0f3f7")
        self.answer_value_label.grid(row=1, column=0, sticky=tk.W, padx=14, pady=(2, 10))

        # ---- 输入行 + 提交 ----
        entry_card = ctk.CTkFrame(wrap, fg_color="transparent")
        entry_card.grid(row=5, column=0, sticky=(tk.W, tk.E), padx=14, pady=(12, 0))
        entry_card.columnconfigure(0, weight=1)

        # 内容变化用 StringVar 的 trace 监听：
        # Tk 8.6 的 Entry 没有 <<Modified>> 事件（该事件属于 Text 控件），
        # 绑在 Entry 上永远不会触发，提示层就永远压着用户输入的文字。
        self.answer_var = tk.StringVar(value="")
        self.answer_entry = ctk.CTkEntry(
            entry_card, height=40, corner_radius=10,
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=15),
            fg_color="#1b1f25", border_color="#39404f", border_width=1,
            text_color="#f0f3f7",
            textvariable=self.answer_var)
        self.answer_entry.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 8))
        self.answer_entry.bind('<Return>', self._submit_current)
        self.answer_entry.bind('<Key>', lambda e: self._entry_key_down(self.answer_entry, e))

        # CTk 6.0 的占位符在获得焦点时会被删掉，且标志
        # (_placeholder_text_active) 与内部 Entry 状态容易脱同步，导致 get()
        # 恒返回空串、用户输入被吞。改为自绘提示层，行为完全可控。
        self.entry_hint = ctk.CTkLabel(
            entry_card, text="在这里默写单词…（回车提交）", anchor="w",
            fg_color="#1b1f25", corner_radius=0,
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=15),
            text_color="#6f7986")
        self.entry_hint.place(relx=0.0, rely=0.5, x=14, anchor="w")
        self.entry_hint.bind('<Button-1>', lambda e: self.answer_entry.focus_set())
        self.answer_var.trace_add("write", lambda *a: self._sync_entry_hint())
        # 焦点离开输入框 → 结束「正在输入」状态，内容为空则恢复提示层
        self.answer_entry.bind(
            '<FocusOut>', lambda e: self.root.after(60, self._on_entry_focus_out), add='+')
        # IME 组词区间：Tk 8.6 用这两个虚拟事件标记（见 tk8.6/entry.tcl）。
        # 组词串画在光标处（输入框最左侧），必须让提示层同时让位。
        self.answer_entry.bind('<<TkStartIMEMarkedText>>',
                               lambda e: self._set_entry_typing(True), add='+')
        self.answer_entry.bind('<<TkEndIMEMarkedText>>',
                               lambda e: self._set_entry_typing(False), add='+')

        self.btn_submit = ctk.CTkButton(
            entry_card, text="提交", width=84, height=40, corner_radius=10,
            command=self._submit_current,
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=15),
            fg_color="#27ae60", hover_color="#219a52", text_color="#ffffff")
        self.btn_submit.grid(row=0, column=1)

        self._register_font('answer_entry', 'Microsoft YaHei UI', 15)
        self._register_font('entry_hint', 'Microsoft YaHei UI', 15)
        self._register_font('btn_submit', 'Microsoft YaHei UI', 15)

        # ---- AI 判定详情（可折叠）----
        self.detail_frame = ctk.CTkFrame(wrap, fg_color="#2b313b", corner_radius=10)
        self.detail_frame.grid(row=6, column=0, sticky=(tk.W, tk.E), padx=14, pady=(10, 14))
        # 列要可伸缩，否则展开后文本框只有 200px 宽，不随窗口变化
        self.detail_frame.columnconfigure(0, weight=1)

        self.btn_detail = ctk.CTkButton(
            self.detail_frame, text="AI 判定详情", command=self._toggle_detail,
            width=120, height=28, anchor="w",
            fg_color="transparent", hover_color="#3b424f",
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=12), text_color="#8b95a3")
        self.btn_detail.grid(row=0, column=0, sticky=tk.W, padx=10, pady=6)

        self.detail_arrow = ctk.CTkLabel(
            self.detail_frame, text="▾", width=20,
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=12), text_color="#8b95a3")
        self.detail_arrow.grid(row=0, column=1, sticky=tk.E, padx=(0, 12))
        self.detail_arrow.bind("<Button-1>", lambda e: self._toggle_detail())
        self._register_font('btn_detail', 'Microsoft YaHei UI', 12)
        self._register_font('detail_arrow', 'Microsoft YaHei UI', 12)

        self.ai_frame = ctk.CTkFrame(self.detail_frame, fg_color="transparent")
        self.ai_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), padx=8, pady=(0, 8))
        self.ai_frame.columnconfigure(0, weight=1)
        self.ai_frame.rowconfigure(0, weight=1)

        self.ai_result_text = ctk.CTkTextbox(
            self.ai_frame, height=150,
            font=ctk.CTkFont(family='Consolas', size=11))
        self.ai_result_text.grid(row=0, column=0, sticky=(tk.W, tk.E))
        for _edit_keys in ('<Key>', '<BackSpace>', '<Delete>', '<Control-v>', '<Control-V>',
                           '<Control-x>', '<Control-X>', '<Control-a>', '<Control-A>'):
            self.ai_result_text.bind(_edit_keys, lambda e: "break")
        self._register_font('ai_result_text', 'Consolas', 11)

        self._detail_expanded = False
        self.ai_frame.grid_remove()

        self._more_menu = None
        self._answer_revealed = False

    # ==========================================================
    # 设计稿风格的小控件
    # ==========================================================

    @staticmethod
    def _pill(parent, text, command, width=48, fg_color="#2f3540"):
        """顶栏/卡片里的胶囊小按钮。"""
        btn = ctk.CTkButton(
            parent, text=text, command=command, width=width, height=26,
            corner_radius=7, fg_color=fg_color, hover_color="#3b424f",
            text_color="#cfd6df",
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=12))
        # 记录基准尺寸，窗口缩放时按钮宽高跟着字号一起缩，避免小字配大按钮
        btn._pill_base = (width, 26)
        return btn

    @staticmethod
    def _bind_hint(widget, text):
        """给控件挂一个悬停提示（自绘，tkinter 没有现成 ToolTip）。"""
        try:
            # 必须存引用，否则临时对象被回收，绑定随之失效
            widget._tip = _SimpleTip(widget, text)
        except Exception:
            pass

    def _goto_ai_settings(self):
        """顶栏「AI」胶囊：跳到 AI 设置页。"""
        try:
            self.pages.select("AI设置")
        except Exception:
            pass

    def _reveal_answer(self):
        """「查看答案」：直接显示标准答案（不判定）。"""
        if not self.current_csv_data or self.current_index >= len(self.current_csv_data):
            return
        row = self.current_csv_data[self.current_index]
        correct = row[2] if len(row) > 2 else ""
        clean_display = clean_answer_string(correct, self.ai_assistant)
        self._answer_revealed = True
        try:
            self.answer_value_label.configure(text=clean_display or "· · ·")
        except Exception:
            pass
        try:
            self.ai_result_text.insert(tk.END, f"\n💡 正确答案: {clean_display}\n")
            self.ai_result_text.see(tk.END)
        except Exception:
            pass

    # ==========================================================
    # 「⋯ 更多」浮层
    # ==========================================================

    def _build_more_menu(self):
        """低频操作的浮层面板（自绘，CustomTkinter 6.0 没有 CTkMenu）。"""
        menu = ctk.CTkFrame(self.main_wrap, fg_color="#21252b", corner_radius=12,
                             border_width=1, border_color="#33383f")
        menu.grid_columnconfigure(0, weight=1)

        head = ctk.CTkFrame(menu, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=12, pady=(9, 0))
        head.columnconfigure(0, weight=1)

        ctk.CTkLabel(head, text="更多操作", anchor="w",
                     font=ctk.CTkFont(family='Microsoft YaHei UI', size=12),
                     text_color="#8b95a3").grid(row=0, column=0, sticky="w")

        btn_close = ctk.CTkButton(
            head, text="✕", command=self._close_more_menu, width=24, height=22,
            corner_radius=6, fg_color="transparent", hover_color="#3b424f",
            text_color="#8b95a3",
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=12))
        btn_close.grid(row=0, column=1, sticky="e")

        sep = ctk.CTkFrame(menu, height=1, fg_color="#33383f")
        sep.grid(row=1, column=0, sticky="ew", padx=12, pady=(6, 4))

        items = [
            ("保存进度", self.save_progress, False),
            ("读取进度", self.load_progress, False),
            ("开始新一轮复习", self.start_new_round, False),
            ("导出错题本", self.export_wrong_answers, False),
            ("导出 AI 判定日志", self.export_ai_logs, False),
            ("重置", self.reset_app, True),
        ]
        row = 2
        for idx, (text, cmd, danger) in enumerate(items):
            btn = ctk.CTkButton(
                menu, text=text, height=30, anchor="w",
                command=lambda c=cmd: self._run_more(c),
                fg_color="transparent", hover_color="#2b313b",
                font=ctk.CTkFont(family='Microsoft YaHei UI', size=12),
                text_color="#f09595" if danger else "#dfe4ea")
            btn.grid(row=row, column=0, sticky="ew", padx=6, pady=1)
            row += 1
            if idx < len(items) - 1:
                line = ctk.CTkFrame(menu, height=1, fg_color="#2c313a")
                line.grid(row=row, column=0, sticky="ew", padx=12)
                row += 1
        return menu

    def _toggle_more_menu(self):
        menu = self._more_menu
        if menu is None:
            menu = self._build_more_menu()
            self._more_menu = menu
        try:
            if menu.winfo_ismapped():
                self._close_more_menu()
            else:
                menu.place(relx=1.0, rely=0.0, x=-14, y=42, anchor="ne")
        except Exception:
            pass

    def _close_more_menu(self):
        try:
            if self._more_menu is not None:
                self._more_menu.place_forget()
        except Exception:
            pass

    def _run_more(self, cmd):
        self._close_more_menu()
        try:
            cmd()
        except Exception:
            pass

    def _on_global_escape(self, event=None):
        """Esc 关闭浮层。"""
        self._close_more_menu()

    def _on_global_click(self, event):
        """点击浮层外部时关闭「⋯ 更多」浮层。"""
        menu = getattr(self, "_more_menu", None)
        if menu is None:
            return
        try:
            if not menu.winfo_ismapped():
                return
        except Exception:
            return
        widget = getattr(event, "widget", None)
        if widget is None:
            return
        if self._is_descendant(widget, menu):
            return
        btn_more = getattr(self, "btn_more", None)
        if btn_more is not None and self._is_descendant(widget, btn_more):
            return
        self._close_more_menu()

    @staticmethod
    def _is_descendant(widget, ancestor):
        """判断 widget 是否是 ancestor 的后代（含自身）。"""
        try:
            node = widget
            while node is not None:
                if node is ancestor:
                    return True
                node = getattr(node, "master", None)
            return False
        except Exception:
            return False

    # ==========================================================
    # AI 判定详情折叠
    # ==========================================================

    def _toggle_detail(self):
        self._set_detail_expanded(not self._detail_expanded)

    def _set_detail_expanded(self, expanded):
        self._detail_expanded = expanded
        try:
            if expanded:
                self.ai_frame.grid()
                self.btn_detail.configure(text="AI 判定详情")
                self.detail_arrow.configure(text="▴")
            else:
                self.ai_frame.grid_remove()
                self.btn_detail.configure(text="AI 判定详情")
                self.detail_arrow.configure(text="▾")
        except Exception:
            pass

    # ==========================================================
    # 提交 / 判定
    # ==========================================================

    def _submit_current(self, event=None):
        """提交按钮与回车的统一入口。

        未判定 → 提交作答；已判定 → 进入下一题。

        注意：作为 Entry 的 '<Return>' 绑定回调时，Tkinter 会传入 event 对象，
        因此这里必须允许额外位置参数；返回 "break" 可阻止默认的蜂鸣行为。
        """
        info = getattr(self, "last_judgment_info", None)
        if info and info.get("index") == self.current_index:
            self.next_question()
            return "break"
        if self.submit_answer(self._entry_text(self.answer_entry)):
            self._clear_entry(self.answer_entry)
        return "break"

    def _refresh_verdict(self):
        """刷新判定卡、正确答案卡与提交按钮状态。"""
        if getattr(self, "verdict_card", None) is None:
            return
        info = getattr(self, "last_judgment_info", None)
        judged = bool(info) and info.get("index") == self.current_index

        state = None
        answer = None
        if judged:
            state = "correct" if info.get("is_correct") else "wrong"
            answer = info.get("correct_answer") or ""

        palette = {
            "correct": ("#4ade80", "判定正确"),
            "wrong": ("#f87171", "判定错误"),
        }
        if state in palette:
            fg, text = palette[state]
            self.verdict_card.configure(fg_color="#2b313b")
            self.verdict_label.configure(text=text, text_color=fg)
        else:
            self.verdict_card.configure(fg_color="#2b313b")
            self.verdict_label.configure(text="等待作答", text_color="#9aa4b2")

        # 判定前不显示答案，避免照抄（除非用户主动点了「查看答案」）
        try:
            if judged:
                shown = clean_answer_string(answer, self.ai_assistant) if answer else "· · ·"
            elif getattr(self, "_answer_revealed", False):
                row = self.current_csv_data[self.current_index]
                raw = row[2] if len(row) > 2 else ""
                shown = clean_answer_string(raw, self.ai_assistant) or "· · ·"
            else:
                shown = "· · ·"
            self.answer_value_label.configure(text=shown)
        except Exception:
            pass

        try:
            if judged:
                self.btn_skip.grid_remove()
                self.btn_mark_correct.grid()
                self.btn_mark_wrong.grid()
                self.btn_submit.configure(text="下一题", fg_color="#2980b9", hover_color="#2471a3")
            else:
                self.btn_skip.grid()
                self.btn_mark_correct.grid_remove()
                self.btn_mark_wrong.grid_remove()
                self.btn_submit.configure(text="提交", fg_color="#27ae60", hover_color="#219a52")
        except Exception:
            pass

    # ==========================================================
    # 输入框：灰色提示层 + 真实文本读取
    # ==========================================================
    # 不使用 CTkEntry 自带的 placeholder：它在获得焦点时会被删掉，且标志
    # (_placeholder_text_active) 与内部 Entry 状态容易脱同步，导致 get()
    # 恒返回空串、用户输入被吞。改为自绘提示层，行为完全可控。

    def _entry_text(self, entry):
        """读取输入框真实文本。"""
        var = getattr(self, "answer_var", None)
        if var is not None:
            try:
                return var.get()
            except Exception:
                pass
        try:
            return entry._entry.get()
        except Exception:
            try:
                return entry.get()
            except Exception:
                return ""

    def _sync_entry_hint(self):
        """输入框为空且未在输入时显示灰色提示层，否则隐藏。

        提示层是叠在 Entry 之上的独立 Label，IME 组词串正好画在光标处
        （输入框最左侧），两者一旦同时存在就会互相遮挡。
        判定依据有两个：
          - answer_var（StringVar）非空 → 有真实内容，隐藏
          - _entry_typing 为真 → 正在打字 / IME 组词中，隐藏
        """
        hint = getattr(self, "entry_hint", None)
        if hint is None:
            return
        var = getattr(self, "answer_var", None)
        try:
            empty = (var.get() == "") if var is not None else True
        except Exception:
            empty = True
        try:
            if empty and not getattr(self, "_entry_typing", False):
                hint.place(relx=0.0, rely=0.5, x=14, anchor="w")
            else:
                hint.place_forget()
        except Exception:
            pass

    def _clear_entry(self, entry):
        """清空输入框，并同步灰色提示层的显隐。"""
        self._entry_typing = False
        try:
            entry.delete(0, tk.END)
        except Exception:
            pass
        self._sync_entry_hint()

    def _set_entry_hint(self, entry, text):
        """安全更换输入框提示文字。

        现在提示文字由自绘的 entry_hint 层承担，这里只改文案。
        """
        hint = getattr(self, "entry_hint", None)
        if hint is not None:
            try:
                hint.configure(text=text)
            except Exception:
                pass

    def _set_entry_typing(self, flag):
        """设置「本轮是否正在输入」，并同步提示层显隐。

        True  → 隐藏提示层（正在打字 / IME 组词中）
        False → 内容为空时重新显示提示层
        """
        self._entry_typing = bool(flag)
        self._sync_entry_hint()

    def _on_entry_focus_out(self):
        """焦点离开输入框：结束输入状态，内容为空则恢复提示层。"""
        self._entry_typing = False
        self._sync_entry_hint()

    def _entry_key_down(self, entry, event=None):
        """按键钩子：一旦用户开始输入，就让灰色提示层让位。

        IME 组词阶段 Entry 内容仍是空串，只有「用户已按键」这一信号可用；
        不隐藏提示层，组词串（画在光标处）就会被提示文字压住。
        """
        self._entry_typing = True
        self._sync_entry_hint()
        return

    # ==========================================================
    # 单词 / 词性字号自适应
    # ==========================================================

    def _update_question_fonts(self):
        """单词/词性字号自适应：依据文本实测宽度 + 卡片可用宽高。"""
        try:
            self._do_update_question_fonts()
        except Exception:
            # <Configure> / after 回调可能在窗口销毁后仍触发，静默忽略
            pass

    def _do_update_question_fonts(self):
        card = getattr(self, "word_card", None)
        if card is None:
            return
        card_w = card.winfo_width()
        card_h = card.winfo_height()
        if card_w < 60 or card_h < 40:
            return

        word = self.col1_value.cget("text") or ""
        pos = self.col2_value.cget("text") or ""

        cache_key = (word, pos, card_w, card_h)
        if self._question_size_cache.get("key") == cache_key:
            return
        self._question_size_cache["key"] = cache_key

        # 宽度基准取外层容器，而不是单词卡自身：
        # 单词卡会跟着文字变宽，若拿卡宽当基准，字号不减 → 越算越宽，
        # 最终把内容顶出窗口（实测 apple 就把卡片撑到 1400px）。
        wrap = getattr(self, "main_wrap", None)
        base_w = wrap.winfo_width() if wrap is not None else card_w
        avail_w = max(min(base_w, card_w) - 40, 40)
        avail_h = max(card_h - 40, 20)

        word_size = max(16, min(52, int(avail_h * 0.62)))
        pos_size = max(12, int(word_size * 0.55))

        def apply():
            self.col1_value.configure(
                font=ctk.CTkFont(family="Microsoft YaHei UI", size=word_size, weight="bold"))
            self.col2_value.configure(
                font=ctk.CTkFont(family="Microsoft YaHei UI", size=pos_size))

        for _ in range(8):
            self.root.update_idletasks()
            need_w = self._text_px(word, word_size, True)
            need_p = self._text_px(pos, pos_size, False)
            over_w = need_w > avail_w * 0.96
            over_p = need_p > avail_w * 0.96
            if not over_w and not over_p:
                break
            if over_w:
                word_size = max(14, int(word_size * min(1.0, avail_w * 0.96 / need_w)) - 1)
            if over_p:
                pos_size = max(11, int(pos_size * min(1.0, avail_w * 0.96 / need_p)) - 1)
            pos_size = min(pos_size, max(12, int(word_size * 0.62)))
            apply()
        apply()

    def setup_settings_tab(self, parent):
        """构建 AI 设置页（与学习页同一套视觉语言）。

        卡片式分区：AI 服务商 / Ollama 配置 / 其他 API 密钥，
        控件沿用设计稿的胶囊按钮、深底输入框与灰蓝次级文字。
        """
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        wrap = ctk.CTkFrame(parent, fg_color="#21252b", corner_radius=12,
                             border_width=1, border_color="#33383f")
        wrap.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=8, pady=5)
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(1, weight=1)

        # ---- 顶部工具条：标题 + 返回学习 ----
        bar = ctk.CTkFrame(wrap, fg_color="transparent")
        bar.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=14, pady=(10, 0))
        bar.columnconfigure(0, weight=1)

        ctk.CTkLabel(
            bar, text="AI 设置", anchor="w",
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=14, weight='bold'),
            text_color="#f0f3f7").grid(row=0, column=0, sticky=tk.W)

        self.btn_back = self._pill(bar, "← 学习", self._goto_learning, width=58)
        self.btn_back.grid(row=0, column=1)
        self._bind_hint(self.btn_back, "返回学习页")
        self._register_font('btn_back', 'Microsoft YaHei UI', 12)

        # ---- 可滚动内容区 ----
        scroll = ctk.CTkScrollableFrame(
            wrap, fg_color="transparent", corner_radius=0, border_width=0,
            scrollbar_button_color="#3b424f", scrollbar_button_hover_color="#4a5260")
        scroll.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=14, pady=(8, 12))
        scroll.columnconfigure(0, weight=1)

        providers = self.ai_assistant.get_available_providers()

        # ========== 卡片 1：AI 服务商 ==========
        card1 = self._settings_card(scroll, "AI 服务商", "选择用于判定对错的 AI 引擎", row=0)

        self.lbl_ai_provider = ctk.CTkLabel(
            card1, text="提供商", anchor="w",
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=13),
            text_color="#f0f3f7")
        self.lbl_ai_provider.grid(row=0, column=0, sticky=tk.W, padx=(14, 10), pady=(12, 6))
        self._register_font('lbl_ai_provider', 'Microsoft YaHei UI', 13)

        self.provider_combo = ctk.CTkComboBox(
            card1, values=list(providers.keys()), height=40, corner_radius=10,
            state='readonly', font=ctk.CTkFont(family='Microsoft YaHei UI', size=13),
            fg_color="#1b1f25", border_color="#39404f", button_color="#2f3540",
            button_hover_color="#3b424f", dropdown_fg_color="#2b313b",
            dropdown_hover_color="#3b424f", dropdown_text_color="#f0f3f7",
            text_color="#f0f3f7")
        self.provider_combo.grid(row=0, column=1, sticky=(tk.W, tk.E),
                                 padx=(0, 14), pady=(12, 6))
        self.provider_combo.set(self.ai_assistant.ai_provider)
        self.provider_combo.configure(command=self.on_provider_change)
        self._register_font('provider_combo', 'Microsoft YaHei UI', 13)

        self.provider_desc = ctk.CTkLabel(
            card1, text="", anchor="w", justify="left",
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=12), text_color="#8b95a3")
        self.provider_desc.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E),
                                padx=14, pady=(0, 12))
        self.update_provider_description()
        self._register_font('provider_desc', 'Microsoft YaHei UI', 12)

        # ========== 卡片 2：Ollama 配置 ==========
        card2 = self._settings_card(scroll, "Ollama 配置", "本地运行，免费无限使用，推荐", row=1)

        self.lbl_ollama_url = ctk.CTkLabel(
            card2, text="服务地址", anchor="w",
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=13), text_color="#f0f3f7")
        self.lbl_ollama_url.grid(row=0, column=0, sticky=tk.W, padx=(14, 10), pady=(12, 6))
        self._register_font('lbl_ollama_url', 'Microsoft YaHei UI', 13)

        self.ollama_url_entry = ctk.CTkEntry(
            card2, height=40, corner_radius=10,
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=13),
            fg_color="#1b1f25", border_color="#39404f", border_width=1,
            text_color="#f0f3f7")
        self.ollama_url_entry.grid(row=0, column=1, sticky=(tk.W, tk.E),
                                   padx=(0, 8), pady=(12, 6))
        self.ollama_url_entry.insert(0, self.ai_assistant.ollama_base_url)
        self._register_font('ollama_url_entry', 'Microsoft YaHei UI', 13)

        self.btn_check_ollama = self._pill(card2, "检测连接", self.check_ollama_connection,
                                           width=72, fg_color="#2f3540")
        self.btn_check_ollama.grid(row=0, column=2, padx=(0, 14), pady=(12, 6))
        self._register_font('btn_check_ollama', 'Microsoft YaHei UI', 12)

        self.ollama_status_label = ctk.CTkLabel(
            card2, text="未检测", anchor="w",
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=12), text_color="#7f8896")
        self.ollama_status_label.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E),
                                      padx=14, pady=(0, 6))
        self._register_font('ollama_status_label', 'Microsoft YaHei UI', 12)

        self.lbl_model = ctk.CTkLabel(
            card2, text="模型", anchor="w",
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=13), text_color="#f0f3f7")
        self.lbl_model.grid(row=2, column=0, sticky=tk.W, padx=(14, 10), pady=(6, 12))
        self._register_font('lbl_model', 'Microsoft YaHei UI', 13)

        self.model_combo = ctk.CTkComboBox(
            card2, values=[], height=40, corner_radius=10,
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=13),
            fg_color="#1b1f25", border_color="#39404f", button_color="#2f3540",
            button_hover_color="#3b424f", dropdown_fg_color="#2b313b",
            dropdown_hover_color="#3b424f", dropdown_text_color="#f0f3f7",
            text_color="#f0f3f7")
        self.model_combo.grid(row=2, column=1, sticky=(tk.W, tk.E), padx=(0, 8), pady=(6, 12))
        self._register_font('model_combo', 'Microsoft YaHei UI', 13)

        self.btn_refresh_models = self._pill(card2, "刷新列表", self.refresh_ollama_models,
                                              width=72, fg_color="#2f3540")
        self.btn_refresh_models.grid(row=2, column=2, padx=(0, 14), pady=(6, 12))
        self._register_font('btn_refresh_models', 'Microsoft YaHei UI', 12)

        self.update_model_list()

        # ========== 卡片 3：其他 API 密钥 ==========
        card3 = self._settings_card(scroll, "其他 AI API 密钥", "使用云端模型时才需要填写", row=2)

        self.lbl_api_key = ctk.CTkLabel(
            card3, text="API Key", anchor="w",
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=13), text_color="#f0f3f7")
        self.lbl_api_key.grid(row=0, column=0, sticky=tk.W, padx=(14, 10), pady=(12, 6))
        self._register_font('lbl_api_key', 'Microsoft YaHei UI', 13)

        self.api_key_entry = ctk.CTkEntry(
            card3, height=40, corner_radius=10, show="•",
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=13),
            fg_color="#1b1f25", border_color="#39404f", border_width=1,
            text_color="#f0f3f7")
        self.api_key_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 14), pady=(12, 6))
        if self.ai_assistant.api_key:
            self.api_key_entry.insert(0, self.ai_assistant.api_key)
        self._register_font('api_key_entry', 'Microsoft YaHei UI', 13)

        self.use_ai_var = ctk.BooleanVar(value=self.ai_assistant.use_ai)
        self.ai_switch = ctk.CTkSwitch(
            card3, text="启用 AI 智能判定", variable=self.use_ai_var,
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=13),
            text_color="#f0f3f7", progress_color="#27ae60",
            button_color="#4ade80", button_hover_color="#6ee7a0")
        self.ai_switch.grid(row=1, column=0, columnspan=3, sticky=tk.W,
                            padx=14, pady=(6, 2))
        self._register_font('ai_switch', 'Microsoft YaHei UI', 13)

        self.clean_paren_var = ctk.BooleanVar(value=self.ai_assistant.clean_parentheses)
        self.paren_check = ctk.CTkSwitch(
            card3, text="自动忽略括号说明（推荐开启）\n例：苹果（复数） 等价于 苹果；防止括号内容干扰 AI 判定",
            variable=self.clean_paren_var, command=self._on_toggle_clean_paren,
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=13),
            text_color="#f0f3f7", progress_color="#27ae60",
            button_color="#4ade80", button_hover_color="#6ee7a0")
        self.paren_check.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E),
                              padx=14, pady=(6, 12))
        self._register_font('paren_check', 'Microsoft YaHei UI', 13)

        # ---- 底部保存条 ----
        footer = ctk.CTkFrame(wrap, fg_color="transparent")
        footer.grid(row=2, column=0, sticky=(tk.W, tk.E), padx=14, pady=(0, 12))
        footer.columnconfigure(0, weight=1)

        self.save_hint = ctk.CTkLabel(
            footer, text="修改后需保存才会生效", anchor="w",
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=12), text_color="#7f8896")
        self.save_hint.grid(row=0, column=0, sticky=tk.W)
        self._register_font('save_hint', 'Microsoft YaHei UI', 12)

        self.btn_save_settings = ctk.CTkButton(
            footer, text="保存所有设置", command=self.save_ai_settings,
            width=132, height=40, corner_radius=10,
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=14),
            fg_color="#27ae60", hover_color="#219a52", text_color="#ffffff")
        self.btn_save_settings.grid(row=0, column=1, sticky=tk.E)
        self._register_font('btn_save_settings', 'Microsoft YaHei UI', 14)

    # ==========================================================
    # 设置页辅助
    # ==========================================================

    @staticmethod
    def _settings_card(parent, title, subtitle="", row=0):
        """设置页的分区卡片：标题 + 副标题，返回内容区。

        row 为卡片在父容器中的行号（父容器需已配置 column 0 权重）。
        """
        card = ctk.CTkFrame(parent, fg_color="#2b313b", corner_radius=12)
        card.grid(row=row, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        card.columnconfigure(0, weight=1)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=14, pady=(12, 0))
        head.columnconfigure(0, weight=1)

        ctk.CTkLabel(
            head, text=title, anchor="w",
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=14, weight='bold'),
            text_color="#f0f3f7").grid(row=0, column=0, sticky=tk.W)

        if subtitle:
            ctk.CTkLabel(
                head, text=subtitle, anchor="e",
                font=ctk.CTkFont(family='Microsoft YaHei UI', size=12),
                text_color="#7f8896").grid(row=0, column=1, sticky=tk.E)

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.grid(row=1, column=0, sticky=(tk.W, tk.E))
        # 列 0 = 标签（固定宽），列 1 = 控件（吃掉剩余空间），列 2 = 尾部按钮
        body.columnconfigure(0, minsize=76)
        body.columnconfigure(1, weight=1)
        return body

    def _goto_learning(self):
        """从设置页回到学习页。"""
        try:
            self.pages.select("学习")
        except Exception:
            pass




    def on_provider_change(self, *args):
        self.update_provider_description()
        self.update_model_list()

    def update_provider_description(self):
        providers = self.ai_assistant.get_available_providers()
        provider = self.provider_combo.get()
        if provider in providers:
            desc = providers[provider].get('desc', '')
            name = providers[provider].get('name', provider)
            self.provider_desc.configure(text=f"{name} · {desc}")

    def update_model_list(self):
        providers = self.ai_assistant.get_available_providers()
        provider = self.provider_combo.get()
        
        if provider in providers:
            models = providers[provider].get('models', [])
            self.model_combo.configure(values=models)
            if models:
                default_model = ''
                if provider == 'ollama':
                    default_model = 'qwen2.5:7b' if 'qwen2.5:7b' in models else models[0]
                elif self.ai_assistant.model and self.ai_assistant.model in models:
                    default_model = self.ai_assistant.model
                else:
                    default_model = models[0] if models else ''
                
                self.model_combo.set(default_model)

    def check_ollama_connection(self):
        url = self.ollama_url_entry.get().strip() or 'http://localhost:11434'
        self.ai_assistant.set_ollama_base_url(url)

        self.ollama_status_label.configure(text="状态: 检测中...", text_color="#f39c12")

        if self.ai_assistant._check_ollama_http():
            self.ollama_status_label.configure(text=f"状态: ✅ 已连接 ({url})", text_color="#2ecc71")
            self.refresh_ollama_models()
            return

        exe = self.ai_assistant.find_ollama_executable()
        if not exe:
            self.ollama_status_label.configure(text=f"状态: ❌ 未找到 Ollama 程序", text_color="#e74c3c")
            return

        self.ollama_status_label.configure(text="状态: 🦙 尝试自动启动 Ollama...", text_color="#f39c12")

        def worker():
            started = self.ai_assistant.start_ollama()
            if started:
                for i in range(30):
                    time.sleep(1)
                    if self.ai_assistant._check_ollama_http():
                        self.root.after(0, lambda: self._ollama_conn_success(url))
                        return
            self.root.after(0, lambda: self.ollama_status_label.configure(
                text=f"状态: ❌ 自动启动超时 ({url})", text_color="#e74c3c"
            ))

        threading.Thread(target=worker, daemon=True).start()

    def _ollama_conn_success(self, url):
        self.ollama_status_label.configure(text=f"状态: ✅ 已连接 ({url})", text_color="#2ecc71")
        self.refresh_ollama_models()

    def refresh_ollama_models(self):
        models = self.ai_assistant.get_ollama_models()
        if models:
            self.model_combo.configure(values=sorted(models))
            if not self.model_combo.get() or self.model_combo.get() not in models:
                default = 'qwen2.5:7b' if 'qwen2.5:7b' in models else models[0]
                self.model_combo.set(default)
            
            providers = self.ai_assistant.get_available_providers()
            providers['ollama']['models'] = sorted(models)
            
            self.ollama_status_label.configure(text=f"状态: ✅ 已连接 - 找到 {len(models)} 个模型", text_color="#2ecc71")
        else:
            self.model_combo.configure(values=[])
            self.model_combo.set("")
            self.ollama_status_label.configure(text="状态: ⚠️ 已连接但未找到模型，请先下载模型", text_color="#f39c12")

    def save_ai_settings(self):
        ollama_url = self.ollama_url_entry.get().strip()
        api_key = self.api_key_entry.get().strip()
        provider = self.provider_combo.get()
        model = self.model_combo.get()
        use_ai = self.use_ai_var.get()
        clean_paren = self.clean_paren_var.get()

        self.ai_assistant.set_ollama_base_url(ollama_url)
        self.ai_assistant.set_api_key(api_key)
        self.ai_assistant.set_ai_provider(provider)
        self.ai_assistant.set_model(model)
        self.ai_assistant.set_use_ai(use_ai)
        self.ai_assistant.set_clean_parentheses(clean_paren)

        self.update_ai_status()
        self._sync_paren_ui_from_config()

        providers = self.ai_assistant.get_available_providers()
        provider_name = providers.get(provider, {}).get('name', provider)

        messagebox.showinfo("成功", "设置已保存！\n\n" +
                           f"• AI提供商: {provider_name}\n" +
                           f"• Ollama地址: {ollama_url}\n" +
                           f"• 模型: {model}\n" +
                           f"• API Key: {'已设置' if api_key else '未设置'}\n" +
                           f"• AI模式: {'已启用' if use_ai else '未启用'}\n" +
                           f"• 括号清理: {'已开启' if clean_paren else '已关闭'}")

    def update_ai_status(self):
        providers = self.ai_assistant.get_available_providers()
        provider = self.ai_assistant.ai_provider

        if not self.ai_assistant.use_ai:
            self._ai_status_text = "AI 已禁用"
        elif provider == 'ollama':
            if self.ai_assistant._check_ollama_http():
                self._ai_status_text = "Ollama 已就绪"
            else:
                self._ai_status_text = "Ollama 未连接"
        elif provider == 'local':
            self._ai_status_text = "本地算法"
        elif provider in providers:
            name = providers[provider].get('name', provider)
            self._ai_status_text = f"{name} 已就绪"
        else:
            self._ai_status_text = "AI 状态未知"
        self._refresh_status_line()


    def load_csv(self):
        file_paths = filedialog.askopenfilenames(
            title="选择 CSV 文件（可多选，按住 Ctrl 或 Shift 选多个）",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if not file_paths:
            return

        all_data = []
        loaded_files = []
        skipped = []

        for fp in file_paths:
            try:
                with open(fp, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    rows = [r for r in reader if any(cell.strip() for cell in r)]
                if not rows:
                    skipped.append(f"{os.path.basename(fp)}（空文件）")
                    continue
                if len(rows[0]) < 3:
                    skipped.append(f"{os.path.basename(fp)}（不足3列）")
                    continue
                all_data.extend(rows)
                loaded_files.append(fp)
            except Exception as e:
                skipped.append(f"{os.path.basename(fp)}（{e}）")

        if not loaded_files:
            messagebox.showerror("错误", "没有成功加载任何文件！\n\n" + "\n".join(skipped))
            return

        self.current_csv_data = all_data
        self.csv_file_paths = loaded_files
        self.csv_file_path = loaded_files[0] if len(loaded_files) == 1 else None

        if len(loaded_files) == 1:
            self.file_label.configure(text=os.path.basename(loaded_files[0]))
        else:
            self.file_label.configure(
                text=f"{os.path.basename(loaded_files[0])} · 已合并 {len(loaded_files)} 个")

        self.current_index = 0
        self.wrong_answers = []
        self.current_round = 1
        self.correct_count = 0
        self.wrong_count = 0
        self.total_questions = len(self.current_csv_data)

        self.update_progress()
        self.update_ai_status()
        self.display_current_question()
        self.ai_result_text.delete(1.0, tk.END)

        if len(loaded_files) == 1:
            self.ai_result_text.insert(tk.END, f"✅ 成功加载 {self.total_questions} 条记录\n")
        else:
            self.ai_result_text.insert(tk.END, f"✅ 成功合并 {len(loaded_files)} 个文件，共 {self.total_questions} 条记录\n")
            for fp in loaded_files:
                self.ai_result_text.insert(tk.END, f"   📄 {os.path.basename(fp)}\n")
        if skipped:
            self.ai_result_text.insert(tk.END, f"\n⚠️ 跳过 {len(skipped)} 个文件:\n")
            for s in skipped:
                self.ai_result_text.insert(tk.END, f"   ⨯ {s}\n")
        self.ai_result_text.insert(tk.END, f"\n准备开始第 {self.current_round} 轮学习...\n\n")

        provider = self.ai_assistant.ai_provider

        if self.ai_assistant.use_ai:
            if provider == 'ollama':
                if self.ai_assistant._check_ollama_http():
                    model_info = f" ({self.ai_assistant.model})" if self.ai_assistant.model else ""
                    self.ai_result_text.insert(tk.END, f"🦙 使用Ollama本地AI{model_info}\n")
                    self.ai_result_text.insert(tk.END, "   完全免费、隐私安全、无需联网\n")
                else:
                    self.ai_result_text.insert(tk.END, "🦙 Ollama 未运行，正在尝试自动启动...\n")
                    self._ensure_ollama_running_async(silent=False)
            elif provider != 'local':
                providers = self.ai_assistant.get_available_providers()
                provider_name = providers.get(provider, {}).get('name', 'AI')
                model_info = f" ({self.ai_assistant.model})" if self.ai_assistant.model else ""
                self.ai_result_text.insert(tk.END, f"🤖 使用{provider_name}{model_info}\n")
            else:
                self.ai_result_text.insert(tk.END, f"⚙️ 使用本地相似度算法\n")
        else:
            self.ai_result_text.insert(tk.END, f"⚙️ AI功能已禁用，使用本地算法\n")

        self.ai_result_text.insert(tk.END, "\n" + "="*75 + "\n\n")

    def save_progress(self):
        if not self.current_csv_data:
            messagebox.showwarning("提示", "请先加载 CSV 文件！")
            return
        try:
            csv_basename = os.path.splitext(os.path.basename(self.csv_file_path))[0] if hasattr(self, 'csv_file_path') and self.csv_file_path else (
                f"{len(self.csv_file_paths)}个文件合并" if getattr(self, 'csv_file_paths', None) else "未命名")
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            default_name = f"{timestamp}_{csv_basename}.txt"
            file_path = filedialog.asksaveasfilename(
                title="保存学习进度",
                defaultextension=".txt",
                initialfile=default_name,
                initialdir=os.getcwd(),
                filetypes=[("进度文件", "*.txt"), ("All files", "*.*")]
            )
            if not file_path:
                return

            progress_data = {
                "save_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "csv_file_path": self.csv_file_path if hasattr(self, 'csv_file_path') else "",
                "csv_file_paths": getattr(self, 'csv_file_paths', []) or [],
                "csv_file_name": os.path.basename(self.csv_file_path) if hasattr(self, 'csv_file_path') and self.csv_file_path else (
                    f"{len(getattr(self, 'csv_file_paths', []) or [])}个文件合并" if getattr(self, 'csv_file_paths', None) else ""),
                "current_csv_data": self.current_csv_data,
                "total_questions": self.total_questions,
                "current_index": self.current_index,
                "current_round": self.current_round,
                "correct_count": self.correct_count,
                "wrong_count": self.wrong_count,
                "wrong_answers": self.wrong_answers
            }

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(progress_data, f, ensure_ascii=False, indent=2)

            info_text = (
                f"✅ 学习进度已成功保存！\n\n"
                f"📅 保存时间: {progress_data['save_time']}\n"
                f"📚 CSV 文件: {progress_data['csv_file_name']}\n"
                f"📍 当前进度: 第 {progress_data['current_index'] + 1} / {progress_data['total_questions']} 题\n"
                f"🔁 当前轮次: 第 {progress_data['current_round']} 轮\n"
                f"📈 正确: {progress_data['correct_count']} | 错误: {progress_data['wrong_count']}\n"
                f"📝 错题数: {len(progress_data['wrong_answers'])}\n\n"
                f"💾 文件名: {os.path.basename(file_path)}"
            )
            self.ai_result_text.insert(tk.END, f"\n{'='*75}\n{info_text}\n{'='*75}\n\n")
            self.ai_result_text.see(tk.END)
            messagebox.showinfo("成功", info_text)

        except Exception as e:
            messagebox.showerror("错误", f"保存进度失败:\n{str(e)}")

    def load_progress(self):
        file_path = filedialog.askopenfilename(
            title="读取学习进度",
            filetypes=[("进度文件", "*.txt"), ("All files", "*.*")],
            initialdir=os.getcwd()
        )
        if not file_path:
            return
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            saved_csv_data = data.get("current_csv_data", [])
            use_saved_data = saved_csv_data and isinstance(saved_csv_data, list) and len(saved_csv_data) > 0

            if not use_saved_data:
                csv_path = data.get("csv_file_path", "")
                if not csv_path or not os.path.exists(csv_path):
                    alt = messagebox.askyesno(
                        "CSV 文件未找到",
                        f"进度中的 CSV 文件不存在:\n{csv_path}\n\n是否手动选择新的 CSV 文件？\n（可多选，列顺序一致即可继续使用）"
                    )
                    if alt:
                        re_paths = filedialog.askopenfilenames(
                            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
                        )
                        if not re_paths:
                            return
                        all_rows = []
                        for rp in re_paths:
                            with open(rp, 'r', encoding='utf-8') as f:
                                all_rows.extend(r for r in csv.reader(f) if any(c.strip() for c in r))
                        self.current_csv_data = all_rows
                        csv_path = re_paths[0] if len(re_paths) == 1 else ""
                        data["csv_file_paths"] = list(re_paths)
                    else:
                        return
                else:
                    with open(csv_path, 'r', encoding='utf-8') as f:
                        reader = csv.reader(f)
                        self.current_csv_data = list(reader)

                if len(self.current_csv_data) == 0:
                    messagebox.showerror("错误", "CSV 文件为空！")
                    return
                if len(self.current_csv_data[0]) < 3:
                    messagebox.showerror("错误", "CSV 文件至少需要3列数据！")
                    return
            else:
                self.current_csv_data = saved_csv_data
                csv_path = data.get("csv_file_path", "")
                if not csv_path or not os.path.exists(csv_path):
                    csv_path = ""

            self.csv_file_path = csv_path
            self.csv_file_paths = data.get("csv_file_paths", []) or ([] if not csv_path else [csv_path])
            self.total_questions = len(self.current_csv_data)
            n_files = len(self.csv_file_paths)
            if n_files > 1:
                first_name = os.path.basename(self.csv_file_paths[0]) if self.csv_file_paths else ""
                self.file_label.configure(text=f"{first_name} · 已合并 {n_files} 个")
            elif csv_path:
                self.file_label.configure(text=os.path.basename(csv_path))
            else:
                self.file_label.configure(text="（无关联CSV）")
            self.current_index = min(int(data.get("current_index", 0)), max(self.total_questions - 1, 0))
            self.current_round = int(data.get("current_round", 1))
            self.correct_count = int(data.get("correct_count", 0))
            self.wrong_count = int(data.get("wrong_count", 0))
            self.wrong_answers = data.get("wrong_answers", [])
            if not isinstance(self.wrong_answers, list):
                self.wrong_answers = []

            if self.total_questions == 0:
                messagebox.showerror("错误", "恢复的进度数据为空！")
                return

            self.update_progress()
            self.update_ai_status()
            self.display_current_question()
            self.ai_result_text.delete(1.0, tk.END)

            save_time = data.get("save_time", "未知")
            if n_files > 1:
                csv_display = f"{n_files} 个文件合并"
            elif csv_path:
                csv_display = os.path.basename(csv_path)
            else:
                csv_display = "（无关联CSV）"
            info_text = (
                f"✅ 学习进度已成功恢复！\n\n"
                f"📅 进度保存时间: {save_time}\n"
                f"📚 CSV 文件: {csv_display}\n"
                f"📍 当前进度: 第 {self.current_index + 1} / {self.total_questions} 题\n"
                f"🔁 当前轮次: 第 {self.current_round} 轮\n"
                f"📈 正确: {self.correct_count} | 错误: {self.wrong_count}\n"
                f"📝 错题数: {len(self.wrong_answers)}\n\n"
                f"🎯 继续从第 {self.current_index + 1} 题开始学习吧！"
            )
            self.ai_result_text.insert(tk.END, f"\n{'='*75}\n{info_text}\n{'='*75}\n\n")
            self.ai_result_text.see(tk.END)
            messagebox.showinfo("成功", info_text)

        except json.JSONDecodeError:
            messagebox.showerror("错误", "进度文件格式错误，不是有效的 JSON 文件！")
        except Exception as e:
            messagebox.showerror("错误", f"读取进度失败:\n{str(e)}")

    def display_current_question(self):
        if self.current_index < len(self.current_csv_data):
            row = self.current_csv_data[self.current_index]
            self.col1_value.configure(text=row[0] if len(row) > 0 else "-")
            self.col2_value.configure(text=row[1] if len(row) > 1 else "-")
            self._answer_revealed = False
            self._clear_entry(self.answer_entry)
            self.answer_entry.focus_set()
            self.update_progress()
            self._refresh_verdict()
            self._refit_question_fonts()
        else:
            self.finish_round()

    def _refit_question_fonts(self):
        """题目文本变化后重算字号。布局尚未稳定时交给 <Configure> 兜底。"""
        self._question_size_cache.clear()
        card = getattr(self, "word_card", None)
        if card is None or card.winfo_width() < 60:
            return
        self.root.after_idle(self._update_question_fonts)

    def update_progress(self):
        self._refresh_status_line()

    def _refresh_status_line(self):
        """把轮次 / 进度 / 对错统计 / AI 状态合并成一行状态条。"""
        total = len(self.current_csv_data)
        current = min(self.current_index + 1, total) if total else 0
        text = (f"第 {self.current_round} 轮 · {current}/{total} · "
                f"对 {self.correct_count} 错 {self.wrong_count} · {self._ai_status_text}")
        try:
            self.status_label.configure(text=text)
        except Exception:
            pass

    def submit_answer(self, user_answer=None):
        """提交当前作答。

        user_answer=None → 读输入框文本（老逻辑）。
        传入文本 → 直接判定，不经过输入框。
        返回 True=已发起判定；False=未提交（处理中/无题/空答案）。
        """
        if self.processing:
            return False

        if not self.current_csv_data or self.current_index >= len(self.current_csv_data):
            return False

        if user_answer is None:
            user_answer = self._entry_text(self.answer_entry).strip()
        else:
            user_answer = str(user_answer).strip()
        correct_answer = self.current_csv_data[self.current_index][2] if len(self.current_csv_data[self.current_index]) > 2 else ""

        if not user_answer:
            messagebox.showwarning("提示", "请输入答案！")
            return False

        col1 = self.current_csv_data[self.current_index][0]
        col2 = self.current_csv_data[self.current_index][1]

        self.processing = True

        import re
        user_clean = re.sub(r'\s+', '', user_answer.lower())
        possible_answers = split_answers(correct_answer)
        exact_match = False
        for ans in possible_answers:
            ans_clean = re.sub(r'\s+', '', strip_parentheses(ans, self.ai_assistant).lower())
            if user_clean == ans_clean:
                exact_match = True
                break

        if exact_match:
            self.submit_local(user_answer, correct_answer, col1, col2)
        elif self.ai_assistant.use_ai and self.ai_assistant.ai_provider != 'local':
            thread = threading.Thread(target=self.submit_with_ai, args=(user_answer, correct_answer, col1, col2))
            thread.daemon = True
            thread.start()
        else:
            self.submit_local(user_answer, correct_answer, col1, col2)
        return True

    def submit_with_ai(self, user_answer, correct_answer, col1, col2):
        try:
            self._last_user_answer = user_answer
            self._last_correct_answer = correct_answer
            self.ai_assistant._last_user_answer = user_answer
            self.ai_assistant._last_correct_answer = correct_answer

            if self.ai_assistant.ai_provider == 'ollama' and not self.ai_assistant._check_ollama_http():
                self.root.after(0, lambda: self.ai_result_text.insert(tk.END, "🦙 Ollama 未运行，正在后台启动...\n") or self.ai_result_text.see(tk.END))
                started = self.ai_assistant.start_ollama()
                if started:
                    for i in range(30):
                        time.sleep(1)
                        if self.ai_assistant._check_ollama_http():
                            self.root.after(0, lambda: self.ai_result_text.insert(tk.END, "✅ Ollama 已就绪\n") or self.ai_result_text.see(tk.END))
                            break
                    else:
                        self.root.after(0, lambda: self.ai_result_text.insert(tk.END, "⚠️ Ollama 启动超时，改用本地算法\n") or self.ai_result_text.see(tk.END))
                        self.root.after(0, lambda: self.update_ai_status())
                        self.root.after(0, lambda: self.submit_local(user_answer, correct_answer, col1, col2))
                        return
                else:
                    self.root.after(0, lambda: self.ai_result_text.insert(tk.END, "⚠️ 未找到 Ollama，改用本地算法\n") or self.ai_result_text.see(tk.END))
                    self.root.after(0, lambda: self.update_ai_status())
                    self.root.after(0, lambda: self.submit_local(user_answer, correct_answer, col1, col2))
                    return

            ai_result = self.ai_assistant.ai_judge_with_ai(user_answer, correct_answer, col1, col2)

            self.root.after(0, lambda: self.display_ai_result(
                user_answer, correct_answer, col1, col2, ai_result
            ))
        except Exception as e:
            self.root.after(0, lambda: self.submit_local(user_answer, correct_answer, col1, col2))

    def submit_local(self, user_answer, correct_answer, col1, col2):
        is_correct, similarity, analysis = self.local_judge(user_answer, correct_answer)
        self._last_user_answer = user_answer
        self._last_correct_answer = correct_answer
        
        result = {
            'is_correct': is_correct,
            'confidence': similarity,
            'analysis': analysis,
            'suggestions': '' if is_correct else '建议重新学习该条目',
            'similarity_score': similarity
        }
        
        self.display_ai_result(user_answer, correct_answer, col1, col2, result)

    def local_judge(self, user_answer, correct_answer):
        user_clean = re.sub(r'\s+', '', user_answer.lower())
        
        possible_answers = split_answers(correct_answer)
        best_similarity = 0.0
        best_match = ""
        
        for answer in possible_answers:
            clean_answer = re.sub(r'\s+', '', strip_parentheses(answer, self.ai_assistant).lower())
            
            if user_clean == clean_answer:
                return True, 1.0, f"✨ 完美！回答完全正确！"
            
            sequence_matcher = difflib.SequenceMatcher(None, user_clean, clean_answer)
            similarity = sequence_matcher.ratio()
            
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = answer
        
        clean_best_match = strip_parentheses(best_match, self.ai_assistant)
        if best_similarity >= 0.9:
            return True, best_similarity, f"✅ 基本正确！与标准答案\"{clean_best_match}\"高度相似（可能是同义词、不同表达或格式差异）"
        elif best_similarity >= 0.7:
            return False, best_similarity, f"⚠️ 部分正确，与标准答案\"{clean_best_match}\"存在明显差异\n建议：检查词性是否匹配，确认词汇的准确含义"
        elif best_similarity >= 0.4:
            return False, best_similarity, f"❌ 相似度较低，标准答案是：{clean_best_match}\n可能混淆了词义或词性，建议重新学习该单词"
        else:
            return False, best_similarity, f"❌ 答案差异较大，标准答案：{clean_best_match}\n💡 建议：回顾单词的基本含义和用法"

    def display_ai_result(self, user_answer, correct_answer, col1, col2, ai_result):
        try:
            if ai_result is None:
                self.submit_local(user_answer, correct_answer, col1, col2)
                return

            import re as _re
            user_clean = _re.sub(r'\s+', '', str(user_answer).lower())
            possible_answers = split_answers(correct_answer)
            exact_match = False
            for ans in possible_answers:
                if user_clean == _re.sub(r'\s+', '', strip_parentheses(ans, self.ai_assistant).lower()):
                    exact_match = True
                    break

            if exact_match:
                is_correct = True
                confidence = 1.0
                similarity_score = 1.0
                analysis = '✅ 完全匹配'
                suggestions = ''
            else:
                is_correct = ai_result['is_correct']
                confidence = ai_result.get('confidence', 0.5)
                analysis = ai_result.get('analysis', '')
                suggestions = ai_result.get('suggestions', '')
                similarity_score = ai_result.get('similarity_score', confidence)

            providers = self.ai_assistant.get_available_providers()
            provider = self.ai_assistant.ai_provider
            
            if provider == 'ollama':
                mode = "🦙 Ollama (本地)"
            elif provider != 'local' and self.ai_assistant.use_ai:
                mode = f"🤖 {providers.get(provider, {}).get('name', 'AI')}"
            else:
                mode = "⚙️ 本地算法"

            clean_correct_display = clean_answer_string(correct_answer, self.ai_assistant)
            if is_correct:
                result_text = f"\n{'='*80}\n📚 第{self.current_index+1}题 [{mode}]\n{'='*80}\n{col1} ({col2})\n你的答案: {user_answer}\n\n正确\n{'='*80}\n\n"
            else:
                result_text = f"\n{'='*80}\n📚 第{self.current_index+1}题 [{mode}]\n{'='*80}\n{col1} ({col2})\n你的答案: {user_answer}\n\n错误，正确答案：{clean_correct_display}\n{'='*80}\n\n"

            self.ai_result_text.insert(tk.END, result_text)
            self.ai_result_text.see(tk.END)

            if is_correct:
                self.correct_count += 1
            else:
                self.wrong_count += 1
                wrong_row = self.current_csv_data[self.current_index].copy()
                wrong_row.append(f"你的答案: {user_answer}")
                wrong_row.append(f"正确答案: {correct_answer}")
                self.wrong_answers.append(wrong_row)

            self.last_judgment_info = {
                'is_correct': is_correct,
                'col1': col1,
                'col2': col2,
                'user_answer': user_answer,
                'correct_answer': correct_answer,
                'index': self.current_index
            }

            self.update_progress()
            # 判定结果和正确答案需要停留给用户看，否则刚刷新出来就被下一题覆盖。
            # 用户再次回车/点提交时手动前进。
            self._refresh_verdict()
            try:
                self.answer_entry.focus_set()
            except Exception:
                pass

        finally:
            self.processing = False

    def show_answer(self):
        """查看答案：把正确答案写进 AI 详情区。"""
        if self.current_csv_data and self.current_index < len(self.current_csv_data):
            correct_answer = self.current_csv_data[self.current_index][2] if len(self.current_csv_data[self.current_index]) > 2 else ""
            clean_display = clean_answer_string(correct_answer, self.ai_assistant)
            result_text = f"\n💡 正确答案: {clean_display}\n"
            self.ai_result_text.insert(tk.END, result_text)
            self.ai_result_text.see(tk.END)

    def skip_question(self):
        if self.current_csv_data and self.current_index < len(self.current_csv_data):
            wrong_row = self.current_csv_data[self.current_index].copy()
            wrong_row.append("已跳过")
            wrong_row.append(self.current_csv_data[self.current_index][2] if len(self.current_csv_data[self.current_index]) > 2 else "")
            self.wrong_answers.append(wrong_row)
            self.wrong_count += 1
            self.next_question()
    def mark_as_correct(self):
        if not hasattr(self, 'last_judgment_info') or self.last_judgment_info is None:
            messagebox.showinfo("提示", "没有可以修改的判定结果！")
            return
        
        info = self.last_judgment_info
        if info.get('is_correct') == True:
            messagebox.showinfo("提示", "当前已经标记为正确！")
            return
        
        if info.get('is_correct') == False:
            self.correct_count += 1
            if self.wrong_count > 0:
                self.wrong_count -= 1
            
            for i, wrong_row in enumerate(self.wrong_answers):
                if len(wrong_row) >= 2 and wrong_row[0] == info['col1'] and wrong_row[1] == info['col2']:
                    self.wrong_answers.pop(i)
                    break
        
        self.last_judgment_info['is_correct'] = True
        
        result_text = f"\n{'─'*80}\n"
        result_text += f"📝 ** 手动修改判定 ** 📝\n"
        result_text += f"✅ 已将此题标记为：正确 ✓\n"
        result_text += f"📝 单词: {info['col1']} | 词性: {info['col2']}\n"
        result_text += f"你的答案: {info['user_answer']} | 标准答案: {info['correct_answer']}\n"
        result_text += f"{'─'*80}\n\n"
        
        self.ai_result_text.insert(tk.END, result_text)
        self.ai_result_text.see(tk.END)
        self.update_progress()
        self._refresh_verdict()

    def mark_as_wrong(self):
        if not hasattr(self, 'last_judgment_info') or self.last_judgment_info is None:
            messagebox.showinfo("提示", "没有可以修改的判定结果！")
            return
        
        info = self.last_judgment_info
        if info.get('is_correct') == False:
            messagebox.showinfo("提示", "当前已经标记为错误！")
            return
        
        if info.get('is_correct') == True:
            if self.correct_count > 0:
                self.correct_count -= 1
            
            self.wrong_count += 1
            wrong_row = [info['col1'], info['col2'], info['correct_answer']]
            wrong_row.append(f"你的答案: {info['user_answer']}")
            wrong_row.append(f"(手动标记为错误)")
            self.wrong_answers.append(wrong_row)
        
        self.last_judgment_info['is_correct'] = False
        
        result_text = f"\n{'─'*80}\n"
        result_text += f"📝 ** 手动修改判定 ** 📝\n"
        result_text += f"❌ 已将此题标记为：错误 ✗\n"
        result_text += f"📝 单词: {info['col1']} | 词性: {info['col2']}\n"
        result_text += f"你的答案: {info['user_answer']} | 标准答案: {info['correct_answer']}\n"
        result_text += f"已加入错题本，将在下一轮复习\n"
        result_text += f"{'─'*80}\n\n"
        
        self.ai_result_text.insert(tk.END, result_text)
        self.ai_result_text.see(tk.END)
        self.update_progress()
        self._refresh_verdict()

    def next_question(self):
        self.current_index += 1
        if self.current_index < len(self.current_csv_data):
            self.display_current_question()
        else:
            self.finish_round()

    def finish_round(self):
        accuracy = (self.correct_count / self.total_questions * 100) if self.total_questions > 0 else 0
        
        result_text = f"\n{'='*80}\n"
        result_text += f"🎉 第 {self.current_round} 轮完成！\n"
        result_text += f"{'='*80}\n\n"
        result_text += f"📊 学习统计:\n"
        result_text += f"   • 总题数: {self.total_questions}\n"
        result_text += f"   • 正确数: {self.correct_count}\n"
        result_text += f"   • 错误数: {self.wrong_count}\n"
        result_text += f"   • 正确率: {accuracy:.1f}%\n\n"

        if self.wrong_answers:
            result_text += f"⚠️ 有 {len(self.wrong_answers)} 道错题需要复习\n"
            result_text += f"💪 点击'开始新一轮复习'继续巩固学习！\n"
        else:
            result_text += f"🌟 太棒了！全部答对！你已经掌握了所有内容！\n"

        result_text += f"\n{'='*80}\n\n"

        self.ai_result_text.insert(tk.END, result_text)
        self.ai_result_text.see(tk.END)

        self.col1_value.configure(text="🎊 本轮完成!")
        self.col2_value.configure(text="")
        self._clear_entry(self.answer_entry)
        self._refresh_verdict()
        self._refit_question_fonts()

    def start_new_round(self):
        if not self.wrong_answers:
            messagebox.showinfo("提示", "没有错题需要复习！\n\n太棒了！你已经掌握了所有内容！🎉")
            return

        original_wrong = [row[:3] for row in self.wrong_answers]
        self.current_csv_data = original_wrong
        self.current_index = 0
        self.wrong_answers = []
        self.current_round += 1
        self.correct_count = 0
        self.wrong_count = 0
        self.total_questions = len(self.current_csv_data)

        self.update_progress()
        self.display_current_question()

        result_text = f"\n{'='*80}\n"
        result_text += f"🔄 开始第 {self.current_round} 轮复习\n"
        result_text += f"{'='*80}\n\n"
        result_text += f"📚 本轮题目数: {self.total_questions}\n"
        result_text += f"🎯 目标: 掌握所有错题！\n\n"
        self.ai_result_text.insert(tk.END, result_text)
        self.ai_result_text.see(tk.END)

    def export_wrong_answers(self):
        if not self.wrong_answers:
            messagebox.showinfo("提示", "没有错题可导出！")
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"wrong_answers_round{self.current_round}_{timestamp}.csv"

        save_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile=default_filename
        )

        if save_path:
            try:
                with open(save_path, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    for row in self.wrong_answers:
                        writer.writerow(row[:3])

                messagebox.showinfo("成功", f"✅ 错题本已导出到:\n\n{save_path}\n\n共 {len(self.wrong_answers)} 条记录\n（格式与输入CSV一致，可直接重新加载学习）")
            except Exception as e:
                messagebox.showerror("错误", f"导出失败: {str(e)}")

    def export_ai_logs(self):
        log_content = self.ai_result_text.get(1.0, tk.END).strip()
        if not log_content or log_content == "":
            messagebox.showinfo("提示", "AI判定日志为空！\n请先完成至少一道题目的判定后再导出。")
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_name = "未命名CSV"
        if self.csv_file_path:
            csv_name = os.path.splitext(os.path.basename(self.csv_file_path))[0]
            csv_name = "".join([c for c in csv_name if c.isalnum() or c in ('_', '-')]) or "未命名CSV"
        elif getattr(self, 'csv_file_paths', None):
            csv_name = f"{len(self.csv_file_paths)}files_merged"
        default_filename = f"ai_judge_log_{csv_name}_r{self.current_round}_{timestamp}.txt"

        save_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=default_filename
        )

        if save_path:
            try:
                header = []
                header.append("=" * 72)
                header.append("📚 CSV词汇学习工具 - AI判定日志导出")
                header.append("=" * 72)
                header.append(f"🕒 导出时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                header.append(f"📂 CSV文件: {self.csv_file_path or (f'{len(self.csv_file_paths)}个文件合并' if getattr(self, 'csv_file_paths', None) else '（未加载）')}")
                header.append(f"🔁 当前轮次: {self.current_round}")
                header.append(f"📊 当前进度: 第 {self.current_index + (1 if self.current_index > 0 else 0)} / {self.total_questions} 题")
                header.append(f"✅ 正确数: {self.correct_count}    ❌ 错误数: {self.wrong_count}")
                if self.correct_count + self.wrong_count > 0:
                    rate = self.correct_count / (self.correct_count + self.wrong_count) * 100
                    header.append(f"🎯 正确率: {rate:.1f}%")
                header.append(f"🦙 AI提供商: {self.ai_assistant.ai_provider}")
                header.append(f"🤖 模型: {self.ai_assistant.model}")
                header.append(f"🧹 括号清理: {'已开启' if self.ai_assistant.clean_parentheses else '已关闭'}")
                header.append("=" * 72)
                header.append("")
                header.append("")

                with open(save_path, 'w', encoding='utf-8-sig') as f:
                    f.write("\n".join(header))
                    f.write(log_content)
                    f.write("\n")

                size_kb = os.path.getsize(save_path) / 1024
                messagebox.showinfo(
                    "成功",
                    f"✅ AI判定日志已导出到:\n\n{save_path}\n\n"
                    f"📝 日志大小: {size_kb:.1f} KB\n"
                    f"🔁 当前轮次: 第 {self.current_round} 轮\n"
                    f"🎯 进度: {self.correct_count}✅ / {self.wrong_count}❌"
                )
            except Exception as e:
                messagebox.showerror("错误", f"导出AI日志失败: {str(e)}")

    def reset_app(self):
        self.current_csv_data = []
        self.current_index = 0
        self.wrong_answers = []
        self.current_round = 1
        self.total_questions = 0
        self.correct_count = 0
        self.wrong_count = 0
        self.csv_file_path = None
        self.csv_file_paths = []

        self.file_label.configure(text="未选择文件")
        self.col1_value.configure(text="-")
        self.col2_value.configure(text="-")
        self._clear_entry(self.answer_entry)
        self.last_judgment_info = None
        self.ai_result_text.delete(1.0, tk.END)
        self.update_progress()
        self.update_ai_status()
        self._refresh_verdict()
        self._refit_question_fonts()


import sys

def main():
    root = ctk.CTk()
    app = CSVLearningApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()