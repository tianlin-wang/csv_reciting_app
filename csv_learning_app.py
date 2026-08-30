import csv
import os
import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import difflib
import re
import json
import threading


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
import subprocess


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

    def check_ollama_running(self):
        try:
            if HAS_OLLAMA:
                ollama.list()
                return True
            else:
                return self._check_ollama_http()
        except:
            return self._check_ollama_http()

    def _check_ollama_http(self):
        try:
            url = f"{self.ollama_base_url}/api/tags"
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=3) as response:
                return True
        except:
            return False

    def get_ollama_models(self):
        models = []
        try:
            if HAS_OLLAMA:
                model_list = ollama.list()
                if hasattr(model_list, 'models'):
                    models = [m['model'] for m in model_list.models]
                elif isinstance(model_list, dict) and 'models' in model_list:
                    models = [m['model'] for m in model_list['models']]
            else:
                models = self._get_models_http()
        except Exception as e:
            print(f"获取Ollama模型失败: {e}")
        
        return models

    def _get_models_http(self):
        try:
            url = f"{self.ollama_base_url}/api/tags"
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
                if 'models' in data:
                    return [m['model'] for m in data['models']]
        except Exception as e:
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

        ollama_models = self.get_ollama_models()
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


class CSVLearningApp:
    def __init__(self, root):
        self.root = root
        self.root.title("📚 词汇学习默写工具 - 🦙 Ollama AI版")
        self.geometry("1100x900")

        self.current_csv_data = []
        self.current_index = 0
        self.wrong_answers = []
        self.current_round = 1
        self.total_questions = 0
        self.correct_count = 0
        self.wrong_count = 0
        self.csv_file_path = None
        self.ai_assistant = OllamaAILearningAssistant()
        self.processing = False

        self.setup_ui()

    def geometry(self, size):
        self.root.geometry(size)

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)

        notebook = ttk.Notebook(main_frame)
        notebook.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        main_frame.rowconfigure(0, weight=1)

        learning_tab = ttk.Frame(notebook, padding="10")
        notebook.add(learning_tab, text="📚 学习模式")

        settings_tab = ttk.Frame(notebook, padding="10")
        notebook.add(settings_tab, text="🤖 AI设置 (Ollama)")

        self.setup_learning_tab(learning_tab)
        self.setup_settings_tab(settings_tab)

    def setup_learning_tab(self, parent):
        file_frame = ttk.LabelFrame(parent, text="📁 文件操作", padding="5")
        file_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        ttk.Button(file_frame, text="选择 CSV 文件", command=self.load_csv).grid(row=0, column=0, padx=3)
        ttk.Button(file_frame, text="💾 保存进度", command=self.save_progress).grid(row=0, column=1, padx=3)
        ttk.Button(file_frame, text="📂 读取进度", command=self.load_progress).grid(row=0, column=2, padx=3)
        self.file_label = ttk.Label(file_frame, text="未选择文件", font=('Microsoft YaHei UI', 9), foreground='#555')
        self.file_label.grid(row=0, column=3, padx=10, sticky=tk.W)

        info_frame = ttk.LabelFrame(parent, text="📊 进度信息", padding="5")
        info_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        self.round_label = ttk.Label(info_frame, text="轮次: 1", font=('Microsoft YaHei UI', 10, 'bold'))
        self.round_label.grid(row=0, column=0, padx=10)
        self.progress_label = ttk.Label(info_frame, text="进度: 0/0", font=('Microsoft YaHei UI', 10))
        self.progress_label.grid(row=0, column=1, padx=10)
        self.stats_label = ttk.Label(info_frame, text="正确: 0 | 错误: 0", font=('Microsoft YaHei UI', 10))
        self.stats_label.grid(row=0, column=2, padx=10)
        self.ai_status_label = ttk.Label(info_frame, text="🦙 AI: Ollama", font=('Microsoft YaHei UI', 10), foreground='green')
        self.ai_status_label.grid(row=0, column=3, padx=10)

        question_frame = ttk.LabelFrame(parent, text="❓ 当前题目", padding="15")
        question_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        parent.rowconfigure(2, weight=1)

        self.col1_label = ttk.Label(question_frame, text="📝 单词:", font=('Microsoft YaHei UI', 12, 'bold'), foreground='#2E86AB')
        self.col1_label.grid(row=0, column=0, sticky=tk.W, pady=8)
        self.col1_value = ttk.Label(question_frame, text="-", font=('Microsoft YaHei UI', 16, 'bold'), wraplength=600, foreground='#1A5276')
        self.col1_value.grid(row=0, column=1, sticky=tk.W, pady=8, padx=10)

        self.col2_label = ttk.Label(question_frame, text="🏷️ 词性:", font=('Microsoft YaHei UI', 12, 'bold'), foreground='#E74C3C')
        self.col2_label.grid(row=1, column=0, sticky=tk.W, pady=8)
        self.col2_value = ttk.Label(question_frame, text="-", font=('Microsoft YaHei UI', 14, 'italic'), wraplength=600, foreground='#C0392B')
        self.col2_value.grid(row=1, column=1, sticky=tk.W, pady=8, padx=10)

        answer_frame = ttk.LabelFrame(parent, text="✍️ 你的答案 (第三列)", padding="15")
        answer_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        self.answer_entry = ttk.Entry(answer_frame, font=('Microsoft YaHei UI', 12), width=80)
        self.answer_entry.grid(row=0, column=0, padx=5, pady=5, sticky=(tk.W, tk.E))
        answer_frame.columnconfigure(0, weight=1)
        self.answer_entry.bind('<Return>', lambda e: self.submit_answer())

        button_frame = ttk.Frame(parent)
        button_frame.grid(row=4, column=0, columnspan=2, pady=10)

        style = ttk.Style()
        style.configure('Submit.TButton', font=('Microsoft YaHei UI', 10, 'bold'))

        submit_btn = ttk.Button(button_frame, text="✅ 提交答案", command=self.submit_answer, style='Submit.TButton')
        submit_btn.grid(row=0, column=0, padx=8, pady=5)

        ttk.Button(button_frame, text="⏭️ 跳过此题", command=self.skip_question).grid(row=0, column=1, padx=8, pady=5)
        ttk.Button(button_frame, text="💡 查看答案", command=self.show_answer).grid(row=0, column=2, padx=8, pady=5)
        ttk.Button(button_frame, text="➡️ 下一题", command=self.next_question).grid(row=0, column=3, padx=8, pady=5)

        ai_frame = ttk.LabelFrame(parent, text="🦙 AI 判定结果 (Ollama 本地智能分析)", padding="10")
        ai_frame.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        parent.rowconfigure(5, weight=2)

        self.ai_result_text = scrolledtext.ScrolledText(ai_frame, height=12, width=100, font=('Consolas', 10))
        self.ai_result_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        ai_frame.columnconfigure(0, weight=1)
        ai_frame.rowconfigure(0, weight=1)
        manual_judge_frame = ttk.Frame(ai_frame)
        manual_judge_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=5)

        self.btn_mark_correct = ttk.Button(manual_judge_frame, text="✅ 标记为正确", command=self.mark_as_correct)
        self.btn_mark_correct.pack(side=tk.LEFT, padx=5)

        self.btn_mark_wrong = ttk.Button(manual_judge_frame, text="❌ 标记为错误", command=self.mark_as_wrong)
        self.btn_mark_wrong.pack(side=tk.LEFT, padx=5)

        self.last_judgment_info = None

        action_frame = ttk.LabelFrame(parent, text="🎯 操作面板", padding="8")
        action_frame.grid(row=6, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        ttk.Button(action_frame, text="🔄 开始新一轮复习", command=self.start_new_round).grid(row=0, column=0, padx=6)
        ttk.Button(action_frame, text="📥 导出错题本", command=self.export_wrong_answers).grid(row=0, column=1, padx=6)
        ttk.Button(action_frame, text="🗑️ 重置", command=self.reset_app).grid(row=0, column=2, padx=6)

    def setup_settings_tab(self, parent):
        provider_frame = ttk.LabelFrame(parent, text="🌐 选择AI服务商", padding="15")
        provider_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=10, padx=10)
        parent.columnconfigure(0, weight=1)

        providers = self.ai_assistant.get_available_providers()

        ttk.Label(provider_frame, text="AI提供商:", font=('Microsoft YaHei UI', 10, 'bold')).grid(row=0, column=0, sticky=tk.W, pady=5)
        
        self.provider_combo = ttk.Combobox(provider_frame, values=list(providers.keys()), width=45, state='readonly')
        self.provider_combo.grid(row=0, column=1, padx=10, pady=5, sticky=(tk.W, tk.E))
        self.provider_combo.set(self.ai_assistant.ai_provider)
        self.provider_combo.bind('<<ComboboxSelected>>', self.on_provider_change)

        self.provider_desc = ttk.Label(provider_frame, text="", font=('Microsoft YaHei UI', 9), foreground='blue')
        self.provider_desc.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=2)
        self.update_provider_description()

        ollama_frame = ttk.LabelFrame(parent, text="🦙 Ollama 配置 (推荐)", padding="15")
        ollama_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=10, padx=10)

        ttk.Label(ollama_frame, text="Ollama服务地址:", font=('Microsoft YaHei UI', 10)).grid(row=0, column=0, sticky=tk.W, pady=5)
        self.ollama_url_entry = ttk.Entry(ollama_frame, width=55)
        self.ollama_url_entry.grid(row=0, column=1, padx=10, pady=5, sticky=(tk.W, tk.E))
        self.ollama_url_entry.insert(0, self.ai_assistant.ollama_base_url)

        ttk.Button(ollama_frame, text="检测连接", command=self.check_ollama_connection).grid(row=0, column=2, padx=5)
        
        self.ollama_status_label = ttk.Label(ollama_frame, text="状态: 未检测", font=('Microsoft YaHei UI', 9))
        self.ollama_status_label.grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=2)

        ttk.Label(ollama_frame, text="选择模型:", font=('Microsoft YaHei UI', 10)).grid(row=2, column=0, sticky=tk.W, pady=5)
        
        self.model_combo = ttk.Combobox(ollama_frame, values=[], width=52)
        self.model_combo.grid(row=2, column=1, padx=10, pady=5, sticky=(tk.W, tk.E), columnspan=2)
        
        ttk.Button(ollama_frame, text="刷新模型列表", command=self.refresh_ollama_models).grid(row=3, column=0, columnspan=3, pady=5)

        self.update_model_list()

        other_api_frame = ttk.LabelFrame(parent, text="🔑 其他AI API密钥 (可选)", padding="15")
        other_api_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=10, padx=10)

        ttk.Label(other_api_frame, text="API Key:", font=('Microsoft YaHei UI', 10)).grid(row=0, column=0, sticky=tk.W, pady=5)
        self.api_key_entry = ttk.Entry(other_api_frame, width=55, show="*")
        self.api_key_entry.grid(row=0, column=1, padx=10, pady=5, sticky=(tk.W, tk.E))
        if self.ai_assistant.api_key:
            self.api_key_entry.insert(0, self.ai_assistant.api_key)

        self.use_ai_var = tk.BooleanVar(value=self.ai_assistant.use_ai)
        ai_check = ttk.Checkbutton(other_api_frame, text="启用AI智能判定", variable=self.use_ai_var)
        ai_check.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(10, 0))

        self.clean_paren_var = tk.BooleanVar(value=self.ai_assistant.clean_parentheses)
        paren_check = ttk.Checkbutton(other_api_frame, text="自动忽略括号说明（推荐开启）\n例：苹果（复数） 等价于 苹果；防止括号内容干扰AI判定", variable=self.clean_paren_var)
        paren_check.grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(5, 5))

        ttk.Button(other_api_frame, text="💾 保存所有设置", command=self.save_ai_settings).grid(row=3, column=0, columnspan=2, pady=10)

        install_frame = ttk.LabelFrame(parent, text="📦 安装依赖库", padding="15")
        install_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=10, padx=10)

        status_text = f"Ollama Python库: {'✅ 已安装' if HAS_OLLAMA else '❌ 未安装'}\n"
        status_text += f"通义千问(dashscope): {'✅ 已安装' if HAS_DASHSCOPE else '❌ 未安装'}\n"
        status_text += f"智谱AI(zhipuai): {'✅ 已安装' if HAS_ZHIPU else '❌ 未安装'}\n"
        status_text += f"OpenAI: {'✅ 已安装' if HAS_OPENAI else '❌ 未安装'}"

        self.install_status = ttk.Label(install_frame, text=status_text, font=('Consolas', 9))
        self.install_status.grid(row=0, column=0, sticky=tk.W, pady=5)

        btn_frame = ttk.Frame(install_frame)
        btn_frame.grid(row=1, column=0, sticky=tk.W, pady=5)

        if not HAS_OLLAMA:
            ttk.Button(btn_frame, text="安装Ollama库", command=lambda: self.install_package('ollama')).grid(row=0, column=0, padx=5)
        
        if not HAS_DASHSCOPE:
            ttk.Button(btn_frame, text="安装通义千问", command=lambda: self.install_package('dashscope')).grid(row=0, column=1, padx=5)
        
        if not HAS_ZHIPU:
            ttk.Button(btn_frame, text="安装智谱AI", command=lambda: self.install_package('zhipuai')).grid(row=0, column=2, padx=5)
        
        if not HAS_OPENAI:
            ttk.Button(btn_frame, text="安装OpenAI", command=lambda: self.install_package('openai')).grid(row=0, column=3, padx=5)

        usage_info = """
🦙 Ollama 使用指南:

【推荐】为什么选Ollama?
   ✅ 完全免费 - 无需API费用
   ✅ 完全本地 - 隐私安全
   ✅ 无限使用 - 不受限制
   ✅ 中文优秀 - 支持Qwen等中文模型
   ✅ 离线可用 - 断网也能用

【快速开始】
1. 安装Ollama: https://ollama.ai
2. 运行命令: ollama run qwen2.5:7b
3. 在本应用中选择Ollama即可！

【推荐模型】
• qwen2.5:7b - 通义千问2.5 (中文优秀⭐)
• qwen2.5:14b - 更强大的中文能力
• llama3.2 - Meta最新模型
• mistral - 欧洲最强开源模型

💡 其他提供商需要API Key和联网！
"""
        usage_label = ttk.Label(install_frame, text=usage_info, font=('Consolas', 9), justify=tk.LEFT)
        usage_label.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=10)

    def on_provider_change(self, event=None):
        self.update_provider_description()
        self.update_model_list()

    def update_provider_description(self):
        providers = self.ai_assistant.get_available_providers()
        provider = self.provider_combo.get()
        if provider in providers:
            desc = providers[provider].get('desc', '')
            name = providers[provider].get('name', provider)
            self.provider_desc.config(text=f"📍 {name} - {desc}")

    def update_model_list(self):
        providers = self.ai_assistant.get_available_providers()
        provider = self.provider_combo.get()
        
        if provider in providers:
            models = providers[provider].get('models', [])
            self.model_combo['values'] = models
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
        
        self.ollama_status_label.config(text="状态: 检测中...", foreground='orange')
        self.root.update()
        
        if self.ai_assistant.check_ollama_running():
            self.ollama_status_label.config(text=f"状态: ✅ 已连接 ({url})", foreground='green')
            self.refresh_ollama_models()
        else:
            self.ollama_status_label.config(text=f"状态: ❌ 无法连接 ({url})", foreground='red')

    def refresh_ollama_models(self):
        models = self.ai_assistant.get_ollama_models()
        if models:
            self.model_combo['values'] = sorted(models)
            if not self.model_combo.get() or self.model_combo.get() not in models:
                default = 'qwen2.5:7b' if 'qwen2.5:7b' in models else models[0]
                self.model_combo.set(default)
            
            providers = self.ai_assistant.get_available_providers()
            providers['ollama']['models'] = sorted(models)
            
            self.ollama_status_label.config(text=f"状态: ✅ 已连接 - 找到 {len(models)} 个模型", foreground='green')
        else:
            self.ollama_status_label.config(text="状态: ⚠️ 已连接但未找到模型，请先下载模型", foreground='orange')

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
            self.ai_status_label.config(text="AI: 已禁用", foreground='gray')
        elif provider == 'ollama':
            if self.ai_assistant.check_ollama_running():
                model_info = f" ({self.ai_assistant.model})" if self.ai_assistant.model else ""
                self.ai_status_label.config(text=f"🦙 Ollama{model_info}", foreground='green')
            else:
                self.ai_status_label.config(text="🦙 Ollama (未连接)", foreground='orange')
        elif provider == 'local':
            self.ai_status_label.config(text="AI: 本地算法", foreground='gray')
        elif provider in providers:
            name = providers[provider].get('name', provider)
            model_info = f" ({self.ai_assistant.model})" if self.ai_assistant.model else ""
            self.ai_status_label.config(text=f"AI: {name}{model_info}", foreground='green')
        else:
            self.ai_status_label.config(text="AI: 未知", foreground='orange')

    def install_package(self, package_name):
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", package_name],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                messagebox.showinfo("成功", f"{package_name} 库安装成功！\n请重启程序以使用该功能。")
            else:
                messagebox.showerror("错误", f"安装失败:\n{result.stderr}")
        except Exception as e:
            messagebox.showerror("错误", f"安装过程出错:\n{str(e)}")

    def load_csv(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    self.current_csv_data = list(reader)

                if len(self.current_csv_data) == 0:
                    messagebox.showerror("错误", "CSV 文件为空！")
                    return

                if len(self.current_csv_data[0]) < 3:
                    messagebox.showerror("错误", "CSV 文件至少需要3列数据！")
                    return

                self.csv_file_path = file_path
                self.file_label.config(text=os.path.basename(file_path))
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
                
                self.ai_result_text.insert(tk.END, f"✅ 成功加载 {self.total_questions} 条记录\n")
                self.ai_result_text.insert(tk.END, f"准备开始第 {self.current_round} 轮学习...\n\n")
                
                provider = self.ai_assistant.ai_provider
                
                if self.ai_assistant.use_ai:
                    if provider == 'ollama':
                        if self.ai_assistant.check_ollama_running():
                            model_info = f" ({self.ai_assistant.model})" if self.ai_assistant.model else ""
                            self.ai_result_text.insert(tk.END, f"🦙 使用Ollama本地AI{model_info}\n")
                            self.ai_result_text.insert(tk.END, "   完全免费、隐私安全、无需联网\n")
                        else:
                            self.ai_result_text.insert(tk.END, f"⚠️ Ollama未运行，将使用本地算法\n")
                            self.ai_result_text.insert(tk.END, "   请启动Ollama或在'AI设置'中切换\n")
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

            except Exception as e:
                messagebox.showerror("错误", f"无法读取文件: {str(e)}")

    def save_progress(self):
        if not self.current_csv_data:
            messagebox.showwarning("提示", "请先加载 CSV 文件！")
            return
        try:
            csv_basename = os.path.splitext(os.path.basename(self.csv_file_path))[0] if hasattr(self, 'csv_file_path') and self.csv_file_path else "未命名"
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
                "csv_file_name": os.path.basename(self.csv_file_path) if hasattr(self, 'csv_file_path') else "",
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

            csv_path = data.get("csv_file_path", "")
            if not csv_path or not os.path.exists(csv_path):
                alt = messagebox.askyesno(
                    "CSV 文件未找到",
                    f"进度中的 CSV 文件不存在:\n{csv_path}\n\n是否手动选择新的 CSV 文件？\n（如果列顺序一致可继续使用）"
                )
                if alt:
                    csv_path = filedialog.askopenfilename(
                        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
                    )
                    if not csv_path:
                        return
                else:
                    return

            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                self.current_csv_data = list(reader)

            if len(self.current_csv_data) == 0:
                messagebox.showerror("错误", "CSV 文件为空！")
                return
            if len(self.current_csv_data[0]) < 3:
                messagebox.showerror("错误", "CSV 文件至少需要3列数据！")
                return

            self.csv_file_path = csv_path
            self.file_label.config(text=os.path.basename(csv_path))
            self.total_questions = len(self.current_csv_data)
            self.current_index = min(int(data.get("current_index", 0)), self.total_questions - 1)
            self.current_round = int(data.get("current_round", 1))
            self.correct_count = int(data.get("correct_count", 0))
            self.wrong_count = int(data.get("wrong_count", 0))
            self.wrong_answers = data.get("wrong_answers", [])
            if not isinstance(self.wrong_answers, list):
                self.wrong_answers = []

            self.update_progress()
            self.update_ai_status()
            self.display_current_question()
            self.ai_result_text.delete(1.0, tk.END)

            save_time = data.get("save_time", "未知")
            info_text = (
                f"✅ 学习进度已成功恢复！\n\n"
                f"📅 进度保存时间: {save_time}\n"
                f"📚 CSV 文件: {os.path.basename(csv_path)}\n"
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
            self.col1_value.config(text=row[0] if len(row) > 0 else "-")
            self.col2_value.config(text=row[1] if len(row) > 1 else "-")
            self.answer_entry.delete(0, tk.END)
            self.answer_entry.focus_set()
            self.update_progress()
        else:
            self.finish_round()

    def update_progress(self):
        self.round_label.config(text=f"轮次: {self.current_round}")
        self.progress_label.config(text=f"进度: {self.current_index + 1}/{len(self.current_csv_data)}")
        self.stats_label.config(text=f"正确: {self.correct_count} | 错误: {self.wrong_count}")

    def submit_answer(self):
        if self.processing:
            return

        if not self.current_csv_data or self.current_index >= len(self.current_csv_data):
            return

        user_answer = self.answer_entry.get().strip()
        correct_answer = self.current_csv_data[self.current_index][2] if len(self.current_csv_data[self.current_index]) > 2 else ""

        if not user_answer:
            messagebox.showwarning("提示", "请输入答案！")
            return

        col1 = self.current_csv_data[self.current_index][0]
        col2 = self.current_csv_data[self.current_index][1]

        self.processing = True

        if self.ai_assistant.use_ai and self.ai_assistant.ai_provider != 'local':
            thread = threading.Thread(target=self.submit_with_ai, args=(user_answer, correct_answer, col1, col2))
            thread.daemon = True
            thread.start()
        else:
            self.submit_local(user_answer, correct_answer, col1, col2)

    def submit_with_ai(self, user_answer, correct_answer, col1, col2):
        try:
            self._last_user_answer = user_answer
            self._last_correct_answer = correct_answer
            self.ai_assistant._last_user_answer = user_answer
            self.ai_assistant._last_correct_answer = correct_answer
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
            self.next_question()

        finally:
            self.processing = False

    def show_answer(self):
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

        self.col1_value.config(text="🎊 本轮完成!")
        self.col2_value.config(text="")
        self.answer_entry.delete(0, tk.END)

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
                    writer.writerow(['第一列', '第二列', '第三列', '你的答案', '正确答案'])
                    writer.writerows(self.wrong_answers)

                messagebox.showinfo("成功", f"✅ 错题本已导出到:\n\n{save_path}\n\n共 {len(self.wrong_answers)} 条记录")
            except Exception as e:
                messagebox.showerror("错误", f"导出失败: {str(e)}")

    def reset_app(self):
        self.current_csv_data = []
        self.current_index = 0
        self.wrong_answers = []
        self.current_round = 1
        self.total_questions = 0
        self.correct_count = 0
        self.wrong_count = 0
        self.csv_file_path = None

        self.file_label.config(text="未选择文件")
        self.col1_value.config(text="-")
        self.col2_value.config(text="-")
        self.answer_entry.delete(0, tk.END)
        self.ai_result_text.delete(1.0, tk.END)
        self.update_progress()
        self.update_ai_status()


import sys

def main():
    root = tk.Tk()
    
    style = ttk.Style()
    style.theme_use('clam')
    
    app = CSVLearningApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()