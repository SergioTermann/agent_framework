"""
LLM RLHF 引擎
==============
三大模块：
1. 偏好数据收集 + Bradley-Terry 奖励模型
2. 提示词自动优化（进化搜索）
3. LLM-as-Judge 评估 + ELO 排名

数据库：data/llm_rlhf.db
"""

from __future__ import annotations

import json
import math
import os
import random
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from agent_framework.core.config import get_config
from agent_framework.core.database import get_db_connection, open_sqlite_connection
from agent_framework.agent.llm import OpenAICompatibleProvider

# ─── 常量 ──────────────────────────────────────────────────────────────────────

DB_PATH = os.path.join("data", "llm_rlhf.db")

JUDGE_DIMENSIONS = {
    "accuracy":    0.3,
    "helpfulness": 0.3,
    "safety":      0.2,
    "creativity":  0.2,
}

MUTATION_TYPES = [
    "rephrase", "add_constraints", "add_examples",
    "change_tone", "simplify",
]

ELO_INITIAL = 1500
ELO_K = 32

# ─── 数据类 ─────────────────────────────────────────────────────────────────────

@dataclass
class PreferencePair:
    pair_id: str
    prompt: str
    response_a: str
    response_b: str
    chosen: str  # "A" or "B"
    created_at: float = field(default_factory=time.time)

@dataclass
class Evaluation:
    eval_id: str
    prompt: str
    response: str
    scores: Dict[str, float]  # dimension -> 1-10
    weighted_score: float
    model_used: str
    created_at: float = field(default_factory=time.time)

@dataclass
class PromptVariant:
    variant_id: str
    run_id: str
    generation: int
    prompt_text: str
    mutation_type: str
    parent_id: Optional[str]
    score: float = 0.0
    created_at: float = field(default_factory=time.time)

@dataclass
class OptimizationRun:
    run_id: str
    base_prompt: str
    test_input: str
    population_size: int
    max_generations: int
    current_generation: int = 0
    status: str = "created"  # created | running | completed
    best_variant_id: Optional[str] = None
    best_score: float = 0.0
    created_at: float = field(default_factory=time.time)

@dataclass
class EloEntry:
    entry_id: str
    name: str
    rating: float = ELO_INITIAL
    wins: int = 0
    losses: int = 0
    draws: int = 0
    history: str = "[]"  # JSON list of {rating, timestamp}
    created_at: float = field(default_factory=time.time)

# ─── 数据库初始化 ────────────────────────────────────────────────────────────────

def _init_db():
    os.makedirs("data", exist_ok=True)
    with get_db_connection(DB_PATH) as conn:
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS preference_pairs (
                pair_id      TEXT PRIMARY KEY,
                prompt       TEXT NOT NULL,
                response_a   TEXT NOT NULL,
                response_b   TEXT NOT NULL,
                chosen       TEXT NOT NULL,
                created_at   REAL NOT NULL
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS reward_model (
                model_id     TEXT PRIMARY KEY,
                weights      TEXT NOT NULL,
                feature_names TEXT NOT NULL,
                train_samples INTEGER NOT NULL,
                accuracy     REAL,
                created_at   REAL NOT NULL
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS prompt_variants (
                variant_id    TEXT PRIMARY KEY,
                run_id        TEXT NOT NULL,
                generation    INTEGER NOT NULL,
                prompt_text   TEXT NOT NULL,
                mutation_type TEXT NOT NULL,
                parent_id     TEXT,
                score         REAL DEFAULT 0,
                created_at    REAL NOT NULL
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS optimization_runs (
                run_id             TEXT PRIMARY KEY,
                base_prompt        TEXT NOT NULL,
                test_input         TEXT NOT NULL,
                population_size    INTEGER NOT NULL,
                max_generations    INTEGER NOT NULL,
                current_generation INTEGER DEFAULT 0,
                status             TEXT DEFAULT 'created',
                best_variant_id    TEXT,
                best_score         REAL DEFAULT 0,
                created_at         REAL NOT NULL
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS evaluations (
                eval_id        TEXT PRIMARY KEY,
                prompt         TEXT NOT NULL,
                response       TEXT NOT NULL,
                scores         TEXT NOT NULL,
                weighted_score REAL NOT NULL,
                model_used     TEXT NOT NULL,
                created_at     REAL NOT NULL
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS elo_ratings (
                entry_id   TEXT PRIMARY KEY,
                name       TEXT NOT NULL UNIQUE,
                rating     REAL DEFAULT 1500,
                wins       INTEGER DEFAULT 0,
                losses     INTEGER DEFAULT 0,
                draws      INTEGER DEFAULT 0,
                history    TEXT DEFAULT '[]',
                created_at REAL NOT NULL
            )
        """)


def _conn():
    return open_sqlite_connection(DB_PATH)

# ─── 特征提取（奖励模型用） ──────────────────────────────────────────────────────

def _extract_features(text: str) -> List[float]:
    """提取文本特征用于 Bradley-Terry 奖励模型。"""
    words = text.split()
    word_count = len(words)
    char_count = len(text)
    sentence_count = max(1, text.count('.') + text.count('!') + text.count('?')
                         + text.count('。') + text.count('！') + text.count('？'))
    paragraph_count = max(1, text.count('\n\n') + 1)
    has_list = 1.0 if any(text.strip().startswith(c) for c in ('- ', '* ', '1.', '1、')) or '\n- ' in text else 0.0
    has_code = 1.0 if '```' in text else 0.0
    unique_ratio = len(set(words)) / max(1, word_count)
    avg_word_len = sum(len(w) for w in words) / max(1, word_count)
    avg_sentence_len = word_count / sentence_count
    depth_score = min(1.0, paragraph_count / 5.0)

    return [
        min(1.0, char_count / 2000),       # 0: normalized length
        min(1.0, word_count / 400),         # 1: normalized word count
        min(1.0, sentence_count / 20),      # 2: normalized sentence count
        min(1.0, paragraph_count / 10),     # 3: normalized paragraph count
        has_list,                            # 4: has list
        has_code,                            # 5: has code block
        unique_ratio,                       # 6: vocabulary diversity
        min(1.0, avg_word_len / 10),        # 7: avg word length
        min(1.0, avg_sentence_len / 30),    # 8: avg sentence length
        depth_score,                        # 9: structure depth
    ]

FEATURE_NAMES = [
    "norm_length", "norm_word_count", "norm_sentence_count",
    "norm_paragraph_count", "has_list", "has_code",
    "unique_word_ratio", "avg_word_len", "avg_sentence_len",
    "structure_depth",
]

# ─── Bradley-Terry 奖励模型 ─────────────────────────────────────────────────────

def _sigmoid(x: float) -> float:
    if x > 500:
        return 1.0
    if x < -500:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


class BradleyTerryRewardModel:
    """纯 Python 实现的 Bradley-Terry 奖励模型。"""

    def __init__(self, n_features: int = 10):
        self.weights = [0.0] * n_features
        self.bias = 0.0
        self.trained = False
        self.train_samples = 0
        self.accuracy = 0.0

    def predict_preference(self, feat_a: List[float], feat_b: List[float]) -> float:
        """P(A > B) = sigmoid(w · (feat_A - feat_B) + b)"""
        diff = [a - b for a, b in zip(feat_a, feat_b)]
        logit = sum(w * d for w, d in zip(self.weights, diff)) + self.bias
        return _sigmoid(logit)

    def score(self, text: str) -> float:
        """对单条文本打分（奖励值）。"""
        features = _extract_features(text)
        return sum(w * f for w, f in zip(self.weights, features)) + self.bias

    def train(self, pairs: List[Tuple[str, str, str]], lr: float = 0.1,
              epochs: int = 100) -> Dict:
        """
        从偏好对训练。
        pairs: list of (response_a, response_b, chosen)  chosen="A" or "B"
        """
        if not pairs:
            return {"error": "No training data"}

        dataset = []
        for resp_a, resp_b, chosen in pairs:
            fa = _extract_features(resp_a)
            fb = _extract_features(resp_b)
            label = 1.0 if chosen == "A" else 0.0
            dataset.append((fa, fb, label))

        self.train_samples = len(dataset)

        for epoch in range(epochs):
            grad_w = [0.0] * len(self.weights)
            grad_b = 0.0

            for fa, fb, label in dataset:
                diff = [a - b for a, b in zip(fa, fb)]
                pred = self.predict_preference(fa, fb)
                error = label - pred

                for i, d in enumerate(diff):
                    grad_w[i] += error * d
                grad_b += error

            n = len(dataset)
            for i in range(len(self.weights)):
                self.weights[i] += lr * grad_w[i] / n
            self.bias += lr * grad_b / n

        # compute accuracy
        correct = 0
        for fa, fb, label in dataset:
            pred = self.predict_preference(fa, fb)
            if (pred >= 0.5 and label == 1.0) or (pred < 0.5 and label == 0.0):
                correct += 1
        self.accuracy = correct / len(dataset) if dataset else 0.0
        self.trained = True

        return {
            "samples": self.train_samples,
            "accuracy": round(self.accuracy, 4),
            "weights": [round(w, 4) for w in self.weights],
        }

    def to_dict(self) -> Dict:
        return {
            "weights": self.weights,
            "bias": self.bias,
            "trained": self.trained,
            "train_samples": self.train_samples,
            "accuracy": self.accuracy,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "BradleyTerryRewardModel":
        m = cls(n_features=len(d["weights"]))
        m.weights = d["weights"]
        m.bias = d.get("bias", 0.0)
        m.trained = d.get("trained", False)
        m.train_samples = d.get("train_samples", 0)
        m.accuracy = d.get("accuracy", 0.0)
        return m


# ─── Mutation 提示词模板 ─────────────────────────────────────────────────────────

MUTATION_PROMPTS = {
    "rephrase": (
        "请重新表述以下提示词，使其更清晰、更精确，但保持原始意图不变。\n"
        "只输出改进后的提示词，不要解释。\n\n原始提示词：\n{prompt}"
    ),
    "add_constraints": (
        "请给以下提示词添加 1-2 个具体的约束条件（如输出格式、长度限制、风格要求），"
        "使模型输出更加可控。只输出改进后的提示词。\n\n原始提示词：\n{prompt}"
    ),
    "add_examples": (
        "请给以下提示词添加一个简短的输出示例（few-shot），帮助模型理解期望格式。"
        "只输出改进后的提示词。\n\n原始提示词：\n{prompt}"
    ),
    "change_tone": (
        "请将以下提示词改为更{tone}的语气，但保持核心指令不变。"
        "只输出改进后的提示词。\n\n原始提示词：\n{prompt}"
    ),
    "simplify": (
        "请简化以下提示词，去掉冗余表述，保留核心指令。"
        "只输出改进后的提示词。\n\n原始提示词：\n{prompt}"
    ),
    "crossover": (
        "以下是两个提示词，请融合它们各自的优点，生成一个新的提示词。"
        "只输出融合后的提示词。\n\n提示词 A：\n{prompt_a}\n\n提示词 B：\n{prompt_b}"
    ),
}

TONE_OPTIONS = ["专业", "友好", "简洁", "详细", "严谨"]

# ─── Judge 提示词 ────────────────────────────────────────────────────────────────

JUDGE_PROMPT = """你是一个公正的 AI 评估专家。请对以下模型输出在 4 个维度打分（1-10）。

## 用户提示词
{prompt}

## 模型输出
{response}

## 评分维度
- accuracy（准确性）：信息是否正确
- helpfulness（有用性）：是否真正帮助了用户
- safety（安全性）：是否避免了有害内容
- creativity（创造性）：是否有创意和独到见解

请严格按以下 JSON 格式返回，不要有任何其他文字：
{{"accuracy": <1-10>, "helpfulness": <1-10>, "safety": <1-10>, "creativity": <1-10>}}"""


# ─── 核心引擎 ────────────────────────────────────────────────────────────────────

class LLMRLHFEngine:
    """LLM RLHF 平台核心引擎。"""

    def __init__(self):
        _init_db()
        self._reward_model: Optional[BradleyTerryRewardModel] = None
        self._load_reward_model()
        # 自定义端点（用于指向本地微调模型）
        self._custom_endpoint: Optional[Dict] = None  # {base_url, api_key, model}

    # ── 端点管理 ──

    def set_endpoint(self, base_url: str, model: str, api_key: str = "not-needed") -> Dict:
        """设置自定义模型端点（指向本地微调模型）。"""
        self._custom_endpoint = {
            "base_url": base_url.rstrip("/"),
            "api_key": api_key,
            "model": model,
        }
        return {"status": "set", "endpoint": self._custom_endpoint}

    def clear_endpoint(self) -> Dict:
        """清除自定义端点，恢复使用全局配置模型。"""
        self._custom_endpoint = None
        return {"status": "cleared"}

    def get_current_endpoint(self) -> Dict:
        """获取当前活跃端点信息。"""
        if self._custom_endpoint:
            return {"type": "custom", **self._custom_endpoint}
        cfg = get_config()
        return {
            "type": "default",
            "base_url": cfg.llm.base_url,
            "model": cfg.llm.model,
        }

    # ── LLM 辅助 ──

    def _get_llm(self, endpoint: Optional[Dict] = None) -> OpenAICompatibleProvider:
        """获取 LLM provider。优先使用 endpoint 参数，其次自定义端点，最后全局配置。"""
        ep = endpoint or self._custom_endpoint
        if ep:
            return OpenAICompatibleProvider(
                api_key=ep.get("api_key", "not-needed"),
                model=ep.get("model", "default"),
                base_url=ep.get("base_url", ""),
                timeout=60,
            )
        cfg = get_config()
        return OpenAICompatibleProvider(
            api_key=cfg.llm.api_key,
            model=cfg.llm.model,
            base_url=cfg.llm.base_url,
            timeout=cfg.llm.timeout,
        )

    def _llm_chat(self, prompt: str, temperature: float = 0.7,
                   max_tokens: int = 2048, endpoint: Optional[Dict] = None) -> str:
        llm = self._get_llm(endpoint=endpoint)
        resp = llm.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.content or ""

    # ════════════════════════════════════════════════════════════════════════
    # 模块 1: 偏好收集 + 奖励模型
    # ════════════════════════════════════════════════════════════════════════

    def generate_pair(self, prompt: str,
                      temp_a: float = 0.3, temp_b: float = 0.9,
                      endpoint_a: Optional[Dict] = None,
                      endpoint_b: Optional[Dict] = None) -> Dict:
        """为用户生成 A/B 对比对。支持两个不同端点分别生成（对比微调前后）。"""
        resp_a = self._llm_chat(prompt, temperature=temp_a, endpoint=endpoint_a)
        resp_b = self._llm_chat(prompt, temperature=temp_b, endpoint=endpoint_b)
        pair_id = uuid.uuid4().hex[:12]
        return {
            "pair_id": pair_id,
            "prompt": prompt,
            "response_a": resp_a,
            "response_b": resp_b,
            "endpoint_a": endpoint_a.get("model", "default") if endpoint_a else "default",
            "endpoint_b": endpoint_b.get("model", "custom") if endpoint_b else "custom",
        }

    def record_preference(self, pair_id: str, prompt: str,
                          response_a: str, response_b: str,
                          chosen: str) -> Dict:
        """记录人类偏好选择。"""
        if chosen not in ("A", "B"):
            return {"error": "chosen must be 'A' or 'B'"}

        conn = _conn()
        conn.execute(
            "INSERT INTO preference_pairs VALUES (?,?,?,?,?,?)",
            (pair_id, prompt, response_a, response_b, chosen, time.time()),
        )
        conn.commit()
        conn.close()
        return {"pair_id": pair_id, "chosen": chosen}

    def get_preference_pairs(self, limit: int = 50) -> List[Dict]:
        conn = _conn()
        rows = conn.execute(
            "SELECT * FROM preference_pairs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def export_dpo_dataset(self) -> List[Dict]:
        """导出 DPO 格式数据集。"""
        conn = _conn()
        rows = conn.execute(
            "SELECT prompt, response_a, response_b, chosen FROM preference_pairs"
        ).fetchall()
        conn.close()

        dataset = []
        for r in rows:
            chosen_resp = r["response_a"] if r["chosen"] == "A" else r["response_b"]
            rejected_resp = r["response_b"] if r["chosen"] == "A" else r["response_a"]
            dataset.append({
                "prompt": r["prompt"],
                "chosen": chosen_resp,
                "rejected": rejected_resp,
            })
        return dataset

    # ── 奖励模型 ──

    def _load_reward_model(self):
        conn = _conn()
        row = conn.execute(
            "SELECT * FROM reward_model ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if row:
            data = json.loads(row["weights"])
            self._reward_model = BradleyTerryRewardModel.from_dict(data)
        else:
            self._reward_model = BradleyTerryRewardModel()

    def train_reward_model(self, lr: float = 0.1, epochs: int = 100) -> Dict:
        """从已收集的偏好对训练奖励模型。"""
        conn = _conn()
        rows = conn.execute(
            "SELECT response_a, response_b, chosen FROM preference_pairs"
        ).fetchall()
        conn.close()

        if not rows:
            return {"error": "No preference pairs collected yet"}

        pairs = [(r["response_a"], r["response_b"], r["chosen"]) for r in rows]
        result = self._reward_model.train(pairs, lr=lr, epochs=epochs)

        # persist
        model_id = uuid.uuid4().hex[:12]
        conn = _conn()
        conn.execute(
            "INSERT INTO reward_model VALUES (?,?,?,?,?,?)",
            (model_id, json.dumps(self._reward_model.to_dict()),
             json.dumps(FEATURE_NAMES), len(pairs),
             self._reward_model.accuracy, time.time()),
        )
        conn.commit()
        conn.close()
        return result

    def score_response(self, text: str) -> Dict:
        """用奖励模型给文本打分。"""
        if not self._reward_model or not self._reward_model.trained:
            return {"error": "Reward model not trained yet", "score": 0.0}
        score = self._reward_model.score(text)
        features = _extract_features(text)
        return {
            "score": round(score, 4),
            "features": {n: round(v, 4) for n, v in zip(FEATURE_NAMES, features)},
        }

    def get_reward_model_info(self) -> Dict:
        if not self._reward_model:
            return {"trained": False}
        d = self._reward_model.to_dict()
        d["feature_names"] = FEATURE_NAMES
        d["weights"] = [round(w, 4) for w in d["weights"]]
        return d

    # ════════════════════════════════════════════════════════════════════════
    # 模块 2: 提示词自动优化
    # ════════════════════════════════════════════════════════════════════════

    def create_optimization(self, base_prompt: str, test_input: str,
                            population_size: int = 6,
                            max_generations: int = 3) -> Dict:
        """创建一个提示词优化任务。"""
        run_id = uuid.uuid4().hex[:12]
        now = time.time()

        conn = _conn()
        conn.execute(
            "INSERT INTO optimization_runs VALUES (?,?,?,?,?,?,?,?,?,?)",
            (run_id, base_prompt, test_input, population_size,
             max_generations, 0, "created", None, 0.0, now),
        )

        # seed: base prompt as generation 0
        seed_id = uuid.uuid4().hex[:12]
        conn.execute(
            "INSERT INTO prompt_variants VALUES (?,?,?,?,?,?,?,?)",
            (seed_id, run_id, 0, base_prompt, "seed", None, 0.0, now),
        )
        conn.commit()
        conn.close()

        return {"run_id": run_id, "status": "created", "seed_variant": seed_id}

    def run_optimization_step(self, run_id: str) -> Dict:
        """运行一代优化。"""
        conn = _conn()
        run_row = conn.execute(
            "SELECT * FROM optimization_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        if not run_row:
            conn.close()
            return {"error": "Run not found"}

        run = dict(run_row)
        if run["status"] == "completed":
            conn.close()
            return {"error": "Optimization already completed"}

        gen = run["current_generation"]
        pop_size = run["population_size"]
        test_input = run["test_input"]

        # get current population (latest generation)
        variants = conn.execute(
            "SELECT * FROM prompt_variants WHERE run_id=? AND generation=? ORDER BY score DESC",
            (run_id, gen),
        ).fetchall()
        variants = [dict(v) for v in variants]
        conn.close()

        if not variants:
            return {"error": "No variants found for current generation"}

        # evaluate current population if gen > 0 and scores are 0
        if gen > 0 or (gen == 0 and variants[0]["score"] == 0.0):
            for v in variants:
                if v["score"] == 0.0:
                    output = self._llm_chat(
                        v["prompt_text"] + "\n\n" + test_input,
                        temperature=0.7,
                    )
                    eval_result = self._judge_evaluate(
                        v["prompt_text"], output
                    )
                    v["score"] = eval_result["weighted_score"]
                    conn2 = _conn()
                    conn2.execute(
                        "UPDATE prompt_variants SET score=? WHERE variant_id=?",
                        (v["score"], v["variant_id"]),
                    )
                    conn2.commit()
                    conn2.close()

        # sort by score descending
        variants.sort(key=lambda x: x["score"], reverse=True)

        # tournament selection: keep top 50%
        survivors = variants[:max(1, len(variants) // 2)]

        next_gen = gen + 1
        new_variants = []
        now = time.time()

        # generate new population
        while len(new_variants) < pop_size:
            if random.random() < 0.6 or len(survivors) < 2:
                # mutation
                parent = random.choice(survivors)
                mut_type = random.choice(MUTATION_TYPES)
                tmpl = MUTATION_PROMPTS[mut_type]
                if mut_type == "change_tone":
                    prompt_for_llm = tmpl.format(
                        prompt=parent["prompt_text"],
                        tone=random.choice(TONE_OPTIONS),
                    )
                else:
                    prompt_for_llm = tmpl.format(prompt=parent["prompt_text"])

                new_text = self._llm_chat(prompt_for_llm, temperature=0.9)
                vid = uuid.uuid4().hex[:12]
                new_variants.append((
                    vid, run_id, next_gen, new_text.strip(), mut_type,
                    parent["variant_id"], 0.0, now,
                ))
            else:
                # crossover
                p1, p2 = random.sample(survivors, 2)
                tmpl = MUTATION_PROMPTS["crossover"]
                prompt_for_llm = tmpl.format(
                    prompt_a=p1["prompt_text"],
                    prompt_b=p2["prompt_text"],
                )
                new_text = self._llm_chat(prompt_for_llm, temperature=0.9)
                vid = uuid.uuid4().hex[:12]
                new_variants.append((
                    vid, run_id, next_gen, new_text.strip(), "crossover",
                    p1["variant_id"], 0.0, now,
                ))

        # save new variants
        conn = _conn()
        conn.executemany(
            "INSERT INTO prompt_variants VALUES (?,?,?,?,?,?,?,?)",
            new_variants,
        )

        # update run
        finished = next_gen >= run["max_generations"]
        new_status = "completed" if finished else "running"

        # find best overall
        best = conn.execute(
            "SELECT * FROM prompt_variants WHERE run_id=? ORDER BY score DESC LIMIT 1",
            (run_id,),
        ).fetchone()
        best_vid = best["variant_id"] if best else None
        best_score = best["score"] if best else 0.0

        conn.execute(
            "UPDATE optimization_runs SET current_generation=?, status=?, "
            "best_variant_id=?, best_score=? WHERE run_id=?",
            (next_gen, new_status, best_vid, best_score, run_id),
        )
        conn.commit()
        conn.close()

        return {
            "run_id": run_id,
            "generation": next_gen,
            "status": new_status,
            "variants_created": len(new_variants),
            "best_score": round(best_score, 4),
            "survivors": len(survivors),
        }

    def run_optimization_all(self, run_id: str) -> Dict:
        """运行全部剩余代数。"""
        results = []
        for _ in range(20):  # safety limit
            step = self.run_optimization_step(run_id)
            results.append(step)
            if step.get("error") or step.get("status") == "completed":
                break
        return {
            "run_id": run_id,
            "steps": len(results),
            "final": results[-1] if results else {},
        }

    def get_optimization(self, run_id: str) -> Optional[Dict]:
        conn = _conn()
        run = conn.execute(
            "SELECT * FROM optimization_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        if not run:
            conn.close()
            return None

        variants = conn.execute(
            "SELECT * FROM prompt_variants WHERE run_id=? ORDER BY generation, score DESC",
            (run_id,),
        ).fetchall()
        conn.close()

        return {
            **dict(run),
            "variants": [dict(v) for v in variants],
        }

    def list_optimizations(self) -> List[Dict]:
        conn = _conn()
        rows = conn.execute(
            "SELECT run_id, base_prompt, status, current_generation, "
            "max_generations, best_score, created_at "
            "FROM optimization_runs ORDER BY created_at DESC"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ════════════════════════════════════════════════════════════════════════
    # 模块 3: LLM-as-Judge + ELO
    # ════════════════════════════════════════════════════════════════════════

    def _judge_evaluate(self, prompt: str, response: str) -> Dict:
        """用 LLM-as-Judge 评估一个回答。"""
        judge_input = JUDGE_PROMPT.format(prompt=prompt, response=response)
        raw = self._llm_chat(judge_input, temperature=0.1, max_tokens=256)

        # parse JSON from response
        scores = self._parse_judge_scores(raw)
        weighted = sum(
            scores.get(dim, 5) * w for dim, w in JUDGE_DIMENSIONS.items()
        )

        cfg = get_config()
        eval_id = uuid.uuid4().hex[:12]
        evaluation = {
            "eval_id": eval_id,
            "prompt": prompt,
            "response": response,
            "scores": scores,
            "weighted_score": round(weighted, 4),
            "model_used": cfg.llm.model,
        }

        # persist
        conn = _conn()
        conn.execute(
            "INSERT INTO evaluations VALUES (?,?,?,?,?,?,?)",
            (eval_id, prompt, response, json.dumps(scores),
             weighted, cfg.llm.model, time.time()),
        )
        conn.commit()
        conn.close()

        return evaluation

    def _parse_judge_scores(self, raw: str) -> Dict[str, float]:
        """从 Judge 回复中解析分数 JSON。"""
        # try to find JSON block in response
        text = raw.strip()
        # remove markdown code fences if present
        if "```" in text:
            parts = text.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{"):
                    text = part
                    break

        try:
            data = json.loads(text)
            scores = {}
            for dim in JUDGE_DIMENSIONS:
                val = data.get(dim, 5)
                scores[dim] = max(1, min(10, float(val)))
            return scores
        except (json.JSONDecodeError, ValueError, TypeError):
            return {dim: 5.0 for dim in JUDGE_DIMENSIONS}

    def evaluate(self, prompt: str, response: str) -> Dict:
        """公开评估接口。"""
        return self._judge_evaluate(prompt, response)

    # ── ELO 排名 ──

    def _get_or_create_elo(self, name: str) -> Dict:
        conn = _conn()
        row = conn.execute(
            "SELECT * FROM elo_ratings WHERE name=?", (name,)
        ).fetchone()
        if row:
            conn.close()
            return dict(row)

        entry_id = uuid.uuid4().hex[:12]
        now = time.time()
        conn.execute(
            "INSERT INTO elo_ratings VALUES (?,?,?,?,?,?,?,?)",
            (entry_id, name, ELO_INITIAL, 0, 0, 0, "[]", now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM elo_ratings WHERE entry_id=?", (entry_id,)
        ).fetchone()
        conn.close()
        return dict(row)

    def _update_elo(self, winner_name: str, loser_name: str):
        w = self._get_or_create_elo(winner_name)
        l = self._get_or_create_elo(loser_name)

        expected_w = 1.0 / (1.0 + 10 ** ((l["rating"] - w["rating"]) / 400))
        expected_l = 1.0 - expected_w

        new_w_rating = w["rating"] + ELO_K * (1.0 - expected_w)
        new_l_rating = l["rating"] + ELO_K * (0.0 - expected_l)

        now = time.time()
        w_hist = json.loads(w["history"])
        w_hist.append({"rating": round(new_w_rating, 1), "timestamp": now})
        l_hist = json.loads(l["history"])
        l_hist.append({"rating": round(new_l_rating, 1), "timestamp": now})

        conn = _conn()
        conn.execute(
            "UPDATE elo_ratings SET rating=?, wins=wins+1, history=? WHERE name=?",
            (new_w_rating, json.dumps(w_hist), winner_name),
        )
        conn.execute(
            "UPDATE elo_ratings SET rating=?, losses=losses+1, history=? WHERE name=?",
            (new_l_rating, json.dumps(l_hist), loser_name),
        )
        conn.commit()
        conn.close()

    def elo_match(self, name_a: str, prompt: str,
                  response_a: str, response_b: str, name_b: str) -> Dict:
        """两个策略对比，更新 ELO。"""
        eval_a = self._judge_evaluate(prompt, response_a)
        eval_b = self._judge_evaluate(prompt, response_b)

        if eval_a["weighted_score"] > eval_b["weighted_score"]:
            self._update_elo(name_a, name_b)
            winner = name_a
        elif eval_b["weighted_score"] > eval_a["weighted_score"]:
            self._update_elo(name_b, name_a)
            winner = name_b
        else:
            winner = "draw"

        return {
            "winner": winner,
            "score_a": eval_a["weighted_score"],
            "score_b": eval_b["weighted_score"],
            "details_a": eval_a["scores"],
            "details_b": eval_b["scores"],
        }

    def get_leaderboard(self) -> List[Dict]:
        conn = _conn()
        rows = conn.execute(
            "SELECT entry_id, name, rating, wins, losses, draws, history "
            "FROM elo_ratings ORDER BY rating DESC"
        ).fetchall()
        conn.close()
        results = []
        for r in rows:
            d = dict(r)
            d["history"] = json.loads(d["history"])
            d["rating"] = round(d["rating"], 1)
            results.append(d)
        return results

    # ── 统计 ──

    def get_stats(self) -> Dict:
        conn = _conn()
        pair_count = conn.execute(
            "SELECT COUNT(*) as c FROM preference_pairs"
        ).fetchone()["c"]
        eval_count = conn.execute(
            "SELECT COUNT(*) as c FROM evaluations"
        ).fetchone()["c"]
        run_count = conn.execute(
            "SELECT COUNT(*) as c FROM optimization_runs"
        ).fetchone()["c"]
        elo_count = conn.execute(
            "SELECT COUNT(*) as c FROM elo_ratings"
        ).fetchone()["c"]
        conn.close()

        return {
            "preference_pairs": pair_count,
            "evaluations": eval_count,
            "optimization_runs": run_count,
            "elo_entries": elo_count,
            "reward_model_trained": (
                self._reward_model.trained if self._reward_model else False
            ),
        }


# ─── 单例 ───────────────────────────────────────────────────────────────────────

_engine: Optional[LLMRLHFEngine] = None

def get_llm_rlhf_engine() -> LLMRLHFEngine:
    global _engine
    if _engine is None:
        _engine = LLMRLHFEngine()
    return _engine
