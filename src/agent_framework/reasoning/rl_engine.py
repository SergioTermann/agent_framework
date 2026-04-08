"""
强化学习引擎 (Reinforcement Learning Engine)
==============================================
实现基于 Q-Learning / Policy Gradient 的 Agent 强化学习框架。

核心概念：
  - Environment : 环境，定义状态空间、动作空间、奖励函数
  - Agent       : 学习主体，通过与环境交互学习最优策略
  - Episode     : 一次完整的交互回合（从初始状态到终止状态）
  - Replay Buffer: 经验回放缓冲区，存储 (s, a, r, s') 四元组

算法支持：
  - Q-Learning（表格型，适合离散小状态空间）
  - REINFORCE（Policy Gradient，适合复杂/连续状态）
  - LLM-as-Agent（将大模型作为策略函数，通过人类反馈强化）
"""

import json
import math
import random
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agent_framework.core.database import open_sqlite_connection


# ─── 数据类型定义 ──────────────────────────────────────────────────────────────

class RLAlgorithm(str, Enum):
    Q_LEARNING      = "q_learning"       # 表格型 Q 学习
    SARSA           = "sarsa"            # 同策略 TD 控制
    DQN             = "dqn"              # 简化 DQN（线性近似）
    REINFORCE       = "reinforce"        # 蒙特卡洛策略梯度
    UCB_BANDIT      = "ucb_bandit"       # 多臂老虎机 UCB
    LLM_RLHF        = "llm_rlhf"         # 大模型 + 人类反馈强化


@dataclass
class Experience:
    """单条经验：(状态, 动作, 奖励, 下一状态, 是否终止)"""
    state       : str
    action      : str
    reward      : float
    next_state  : str
    done        : bool
    timestamp   : float = field(default_factory=time.time)
    metadata    : Dict  = field(default_factory=dict)


@dataclass
class Episode:
    """一个完整的交互回合"""
    episode_id      : str
    env_id          : str
    algorithm       : str
    experiences     : List[Experience] = field(default_factory=list)
    total_reward    : float = 0.0
    steps           : int   = 0
    status          : str   = "running"   # running | completed | failed
    start_time      : float = field(default_factory=time.time)
    end_time        : Optional[float] = None

    def add(self, exp: Experience):
        self.experiences.append(exp)
        self.total_reward += exp.reward
        self.steps += 1

    def finish(self):
        self.status   = "completed"
        self.end_time = time.time()


@dataclass
class RLEnvironment:
    """环境定义"""
    env_id      : str
    name        : str
    description : str
    state_space : List[str]           # 可选状态列表（离散）
    action_space: List[str]           # 可选动作列表
    max_steps   : int  = 50
    created_at  : float = field(default_factory=time.time)


# ─── 经验回放缓冲区 ────────────────────────────────────────────────────────────

class ReplayBuffer:
    """循环经验缓冲区（Fixed-size FIFO）"""

    def __init__(self, capacity: int = 10_000):
        self._buf: deque = deque(maxlen=capacity)

    def push(self, exp: Experience):
        self._buf.append(exp)

    def sample(self, batch_size: int) -> List[Experience]:
        return random.sample(self._buf, min(batch_size, len(self._buf)))

    def __len__(self) -> int:
        return len(self._buf)


# ─── Q-Table（表格型值函数）────────────────────────────────────────────────────

class QTable:
    """
    离散状态-动作值表。
    Q(s, a) <- Q(s, a) + α * [r + γ * max_a' Q(s', a') - Q(s, a)]
    """

    def __init__(self, alpha: float = 0.1, gamma: float = 0.95, epsilon: float = 0.3):
        self.alpha   = alpha    # 学习率
        self.gamma   = gamma    # 折扣因子
        self.epsilon = epsilon  # 探索率（ε-greedy）
        self._table : Dict[str, Dict[str, float]] = {}

    # ---------- 对外接口 ----------

    def get_q(self, state: str, action: str) -> float:
        return self._table.get(state, {}).get(action, 0.0)

    def choose_action(self, state: str, actions: List[str]) -> str:
        """ε-greedy 策略：以 ε 概率随机探索，否则贪婪选最大 Q"""
        if random.random() < self.epsilon:
            return random.choice(actions)
        qs = {a: self.get_q(state, a) for a in actions}
        return max(qs, key=qs.get)

    def update(self, exp: Experience, actions: List[str]):
        """单步 Q 值更新"""
        s, a, r, s2, done = exp.state, exp.action, exp.reward, exp.next_state, exp.done

        # 目标值：若终止则无未来奖励
        max_next = 0.0 if done else max(self.get_q(s2, a2) for a2 in actions)
        target   = r + self.gamma * max_next

        # 增量更新
        old = self.get_q(s, a)
        new = old + self.alpha * (target - old)
        self._table.setdefault(s, {})[a] = new

    def decay_epsilon(self, rate: float = 0.995, min_eps: float = 0.05):
        """每回合衰减探索率"""
        self.epsilon = max(min_eps, self.epsilon * rate)

    def to_dict(self) -> dict:
        return {
            "alpha": self.alpha, "gamma": self.gamma, "epsilon": self.epsilon,
            "table": self._table,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "QTable":
        qt = cls(d["alpha"], d["gamma"], d["epsilon"])
        qt._table = d["table"]
        return qt


# ─── Policy Gradient（REINFORCE）─────────────────────────────────────────────

class PolicyGradientAgent:
    """
    REINFORCE 算法：蒙特卡洛策略梯度。
    使用 Softmax 对动作打分，回合结束后用折扣累计奖励更新。
    简化实现：用线性得分表代替神经网络参数。
    """

    def __init__(self, gamma: float = 0.95, lr: float = 0.01):
        self.gamma  = gamma
        self.lr     = lr
        # 线性动作得分表：score[state][action] -> float
        self._scores: Dict[str, Dict[str, float]] = {}

    def _get_score(self, state: str, action: str) -> float:
        return self._scores.get(state, {}).get(action, 0.0)

    def _softmax(self, scores: List[float]) -> List[float]:
        """数值稳定的 Softmax"""
        m = max(scores)
        exps = [math.exp(s - m) for s in scores]
        total = sum(exps)
        return [e / total for e in exps]

    def choose_action(self, state: str, actions: List[str]) -> Tuple[str, float]:
        """按策略概率随机采样，返回 (动作, 概率)"""
        scores = [self._get_score(state, a) for a in actions]
        probs  = self._softmax(scores)
        idx    = random.choices(range(len(actions)), weights=probs)[0]
        return actions[idx], probs[idx]

    def update_episode(self, experiences: List[Experience], actions: List[str]):
        """
        回合结束后，用折扣累计奖励 G_t 更新策略参数。
        ∇ log π(a|s) * G_t  ->  score(s,a) += lr * G_t * (1 - π(a|s))
        """
        # 计算每步折扣累计奖励
        G, returns = 0.0, []
        for exp in reversed(experiences):
            G = exp.reward + self.gamma * G
            returns.insert(0, G)

        for exp, G_t in zip(experiences, returns):
            s, a = exp.state, exp.action
            scores = [self._get_score(s, act) for act in actions]
            probs  = self._softmax(scores)
            pi_a   = probs[actions.index(a)] if a in actions else 0.5

            # 梯度上升：增加高奖励动作得分
            self._scores.setdefault(s, {})[a] = (
                self._get_score(s, a) + self.lr * G_t * (1 - pi_a)
            )

    def to_dict(self) -> dict:
        return {"gamma": self.gamma, "lr": self.lr, "scores": self._scores}

    @classmethod
    def from_dict(cls, d: dict) -> "PolicyGradientAgent":
        pg = cls(d["gamma"], d["lr"])
        pg._scores = d["scores"]
        return pg


# ─── SARSA（同策略 TD 控制）────────────────────────────────────────────────

class SARSATable:
    """
    SARSA 算法：On-policy TD(0)。
    与 Q-Learning 不同，SARSA 使用下一步实际选择的动作来更新：
    Q(s,a) <- Q(s,a) + α * [r + γ * Q(s', a') - Q(s,a)]
    """

    def __init__(self, alpha: float = 0.1, gamma: float = 0.95, epsilon: float = 0.3):
        self.alpha   = alpha
        self.gamma   = gamma
        self.epsilon = epsilon
        self._table  : Dict[str, Dict[str, float]] = {}

    def get_q(self, state: str, action: str) -> float:
        return self._table.get(state, {}).get(action, 0.0)

    def choose_action(self, state: str, actions: List[str]) -> str:
        if random.random() < self.epsilon:
            return random.choice(actions)
        qs = {a: self.get_q(state, a) for a in actions}
        return max(qs, key=qs.get)

    def update(self, state: str, action: str, reward: float,
               next_state: str, next_action: str, done: bool):
        """SARSA 更新：使用实际的 next_action"""
        next_q = 0.0 if done else self.get_q(next_state, next_action)
        target = reward + self.gamma * next_q
        old    = self.get_q(state, action)
        self._table.setdefault(state, {})[action] = old + self.alpha * (target - old)

    def decay_epsilon(self, rate: float = 0.995, min_eps: float = 0.05):
        self.epsilon = max(min_eps, self.epsilon * rate)

    def to_dict(self) -> dict:
        return {
            "alpha": self.alpha, "gamma": self.gamma, "epsilon": self.epsilon,
            "table": self._table,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SARSATable":
        st = cls(d["alpha"], d["gamma"], d["epsilon"])
        st._table = d["table"]
        return st


# ─── 简化 DQN（线性函数近似）──────────────────────────────────────────────

class SimpleDQN:
    """
    简化版 DQN：用线性权重代替深层神经网络。
    特征 = 状态-动作对的简单哈希编码。
    支持经验回放和目标网络软更新。
    """

    def __init__(self, alpha: float = 0.01, gamma: float = 0.95,
                 epsilon: float = 0.5, tau: float = 0.1,
                 buffer_size: int = 2000, batch_size: int = 32):
        self.alpha      = alpha
        self.gamma      = gamma
        self.epsilon     = epsilon
        self.tau         = tau       # 目标网络软更新系数
        self.batch_size  = batch_size
        # 在线网络权重 & 目标网络权重
        self._weights    : Dict[str, float] = {}
        self._target_w   : Dict[str, float] = {}
        # 经验回放
        self._buffer     = ReplayBuffer(buffer_size)

    def _feature_key(self, state: str, action: str) -> str:
        return f"{state}||{action}"

    def _predict(self, state: str, action: str, use_target: bool = False) -> float:
        key = self._feature_key(state, action)
        w = self._target_w if use_target else self._weights
        return w.get(key, 0.0)

    def choose_action(self, state: str, actions: List[str]) -> str:
        if random.random() < self.epsilon:
            return random.choice(actions)
        qs = {a: self._predict(state, a) for a in actions}
        return max(qs, key=qs.get)

    def store(self, exp: Experience):
        self._buffer.push(exp)

    def update(self, actions: List[str]):
        """从经验回放中采样并更新权重"""
        if len(self._buffer) < self.batch_size:
            return
        batch = self._buffer.sample(self.batch_size)
        for exp in batch:
            # 目标值：r + γ * max_a' Q_target(s', a')
            if exp.done:
                target = exp.reward
            else:
                max_next = max(self._predict(exp.next_state, a, use_target=True)
                               for a in actions)
                target = exp.reward + self.gamma * max_next

            key    = self._feature_key(exp.state, exp.action)
            old    = self._weights.get(key, 0.0)
            self._weights[key] = old + self.alpha * (target - old)

        # 软更新目标网络
        self._soft_update()

    def _soft_update(self):
        """目标网络软更新：w_target = τ * w_online + (1-τ) * w_target"""
        for key, val in self._weights.items():
            old = self._target_w.get(key, 0.0)
            self._target_w[key] = self.tau * val + (1 - self.tau) * old

    def decay_epsilon(self, rate: float = 0.99, min_eps: float = 0.05):
        self.epsilon = max(min_eps, self.epsilon * rate)

    def get_q(self, state: str, action: str) -> float:
        return self._predict(state, action)

    def to_dict(self) -> dict:
        return {
            "alpha": self.alpha, "gamma": self.gamma, "epsilon": self.epsilon,
            "tau": self.tau, "batch_size": self.batch_size,
            "weights": self._weights, "target_weights": self._target_w,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SimpleDQN":
        dqn = cls(d["alpha"], d["gamma"], d["epsilon"],
                  d.get("tau", 0.1), batch_size=d.get("batch_size", 32))
        dqn._weights  = d.get("weights", {})
        dqn._target_w = d.get("target_weights", {})
        return dqn


# ─── 多臂老虎机（UCB）────────────────────────────────────────────────────

class UCBBandit:
    """
    UCB1 (Upper Confidence Bound) 多臂老虎机算法。
    选择动作依据：argmax_a [ Q(a) + c * sqrt(ln(N) / N(a)) ]
    """

    def __init__(self, c: float = 2.0):
        self.c        = c    # 探索系数
        self._counts  : Dict[str, int]   = {}   # 每个动作被选择的次数
        self._values  : Dict[str, float] = {}   # 每个动作的平均奖励
        self._total   = 0

    def choose_action(self, state: str, actions: List[str]) -> str:
        self._total += 1
        # 未尝试过的动作优先
        for a in actions:
            if self._counts.get(a, 0) == 0:
                return a
        # UCB 选择
        ucb_vals = {}
        for a in actions:
            q  = self._values.get(a, 0.0)
            n  = self._counts.get(a, 1)
            ucb_vals[a] = q + self.c * math.sqrt(math.log(self._total) / n)
        return max(ucb_vals, key=ucb_vals.get)

    def update(self, action: str, reward: float):
        """增量更新平均奖励"""
        n = self._counts.get(action, 0) + 1
        old_val = self._values.get(action, 0.0)
        self._counts[action] = n
        self._values[action] = old_val + (reward - old_val) / n

    def to_dict(self) -> dict:
        return {
            "c": self.c,
            "counts": self._counts,
            "values": self._values,
            "total": self._total,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "UCBBandit":
        b = cls(d.get("c", 2.0))
        b._counts = d.get("counts", {})
        b._values = d.get("values", {})
        b._total  = d.get("total", 0)
        return b


# ─── 持久化层 ─────────────────────────────────────────────────────────────────

DB_PATH = Path("data/rl_engine.db")

def _get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return open_sqlite_connection(DB_PATH)


def _init_db():
    """建表（幂等）"""
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS rl_environments (
                env_id      TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                description TEXT,
                state_space TEXT NOT NULL,   -- JSON 数组
                action_space TEXT NOT NULL,  -- JSON 数组
                max_steps   INTEGER DEFAULT 50,
                created_at  REAL
            );

            CREATE TABLE IF NOT EXISTS rl_agents (
                agent_id    TEXT PRIMARY KEY,
                env_id      TEXT NOT NULL,
                algorithm   TEXT NOT NULL,
                params      TEXT NOT NULL,   -- JSON（Q 表 / 策略参数）
                episodes_done INTEGER DEFAULT 0,
                best_reward REAL DEFAULT 0.0,
                created_at  REAL,
                updated_at  REAL
            );

            CREATE TABLE IF NOT EXISTS rl_episodes (
                episode_id   TEXT PRIMARY KEY,
                agent_id     TEXT NOT NULL,
                env_id       TEXT NOT NULL,
                algorithm    TEXT NOT NULL,
                total_reward REAL DEFAULT 0.0,
                steps        INTEGER DEFAULT 0,
                status       TEXT DEFAULT 'running',
                start_time   REAL,
                end_time     REAL
            );

            CREATE TABLE IF NOT EXISTS rl_experiences (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                episode_id  TEXT NOT NULL,
                step        INTEGER NOT NULL,
                state       TEXT NOT NULL,
                action      TEXT NOT NULL,
                reward      REAL NOT NULL,
                next_state  TEXT NOT NULL,
                done        INTEGER NOT NULL,
                timestamp   REAL,
                metadata    TEXT DEFAULT '{}'
            );
        """)


# ─── RL 管理器（对外统一接口）─────────────────────────────────────────────────

class RLManager:
    """
    强化学习管理器：
      - 管理多个 Environment 和 Agent
      - 驱动 Episode 运行
      - 持久化保存训练历史
    """

    def __init__(self):
        _init_db()
        self._envs   : Dict[str, RLEnvironment]       = {}
        self._q_tabs : Dict[str, QTable]               = {}
        self._pg_ags : Dict[str, PolicyGradientAgent]  = {}
        self._sarsa  : Dict[str, SARSATable]           = {}
        self._dqn    : Dict[str, SimpleDQN]            = {}
        self._bandits: Dict[str, UCBBandit]            = {}
        self._load_all()

    # ─── 环境管理 ───────────────────────────────────────────────────────────────

    def create_environment(
        self,
        name       : str,
        description: str,
        state_space : List[str],
        action_space: List[str],
        max_steps  : int = 50,
    ) -> RLEnvironment:
        env = RLEnvironment(
            env_id      = str(uuid.uuid4()),
            name        = name,
            description = description,
            state_space = state_space,
            action_space= action_space,
            max_steps   = max_steps,
        )
        self._envs[env.env_id] = env
        self._save_environment(env)
        return env

    def get_environment(self, env_id: str) -> Optional[RLEnvironment]:
        return self._envs.get(env_id)

    def list_environments(self) -> List[dict]:
        return [
            {
                "env_id"      : e.env_id,
                "name"        : e.name,
                "description" : e.description,
                "state_count" : len(e.state_space),
                "action_count": len(e.action_space),
                "max_steps"   : e.max_steps,
            }
            for e in self._envs.values()
        ]

    # ─── Agent 管理 ─────────────────────────────────────────────────────────────

    def create_agent(
        self,
        env_id   : str,
        algorithm: str = RLAlgorithm.Q_LEARNING,
        **kwargs,
    ) -> dict:
        """创建并持久化一个 Agent"""
        env = self._envs.get(env_id)
        if not env:
            raise ValueError(f"环境 {env_id} 不存在")

        agent_id = str(uuid.uuid4())
        now = time.time()

        if algorithm == RLAlgorithm.Q_LEARNING:
            agent = QTable(
                alpha   = kwargs.get("alpha",   0.1),
                gamma   = kwargs.get("gamma",   0.95),
                epsilon = kwargs.get("epsilon", 0.3),
            )
            self._q_tabs[agent_id] = agent
            params = agent.to_dict()

        elif algorithm == RLAlgorithm.SARSA:
            agent = SARSATable(
                alpha   = kwargs.get("alpha",   0.1),
                gamma   = kwargs.get("gamma",   0.95),
                epsilon = kwargs.get("epsilon", 0.3),
            )
            self._sarsa[agent_id] = agent
            params = agent.to_dict()

        elif algorithm == RLAlgorithm.DQN:
            agent = SimpleDQN(
                alpha      = kwargs.get("alpha",    0.01),
                gamma      = kwargs.get("gamma",    0.95),
                epsilon    = kwargs.get("epsilon",  0.5),
                tau        = kwargs.get("tau",      0.1),
                batch_size = int(kwargs.get("batch_size", 32)),
            )
            self._dqn[agent_id] = agent
            params = agent.to_dict()

        elif algorithm == RLAlgorithm.REINFORCE:
            agent = PolicyGradientAgent(
                gamma = kwargs.get("gamma", 0.95),
                lr    = kwargs.get("lr",    0.01),
            )
            self._pg_ags[agent_id] = agent
            params = agent.to_dict()

        elif algorithm == RLAlgorithm.UCB_BANDIT:
            agent = UCBBandit(c=kwargs.get("c", 2.0))
            self._bandits[agent_id] = agent
            params = agent.to_dict()

        else:
            # LLM_RLHF：参数占位
            params = {"algorithm": algorithm, **kwargs}

        with _get_conn() as conn:
            conn.execute(
                """INSERT INTO rl_agents
                   (agent_id, env_id, algorithm, params, episodes_done,
                    best_reward, created_at, updated_at)
                   VALUES (?,?,?,?,0,0.0,?,?)""",
                (agent_id, env_id, algorithm, json.dumps(params), now, now),
            )

        return {"agent_id": agent_id, "env_id": env_id, "algorithm": algorithm}

    def list_agents(self, env_id: Optional[str] = None) -> List[dict]:
        with _get_conn() as conn:
            if env_id:
                rows = conn.execute(
                    "SELECT * FROM rl_agents WHERE env_id=?", (env_id,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM rl_agents").fetchall()
        return [dict(r) for r in rows]

    # ─── Episode 运行 ───────────────────────────────────────────────────────────

    def run_episode(
        self,
        agent_id    : str,
        env_id      : str,
        reward_func : Any,  # callable(state, action) -> (next_state, reward, done)
        algorithm   : str = RLAlgorithm.Q_LEARNING,
    ) -> dict:
        """
        运行一个完整 Episode。

        reward_func 签名：
            fn(state: str, action: str) -> (next_state: str, reward: float, done: bool)

        返回 Episode 摘要 dict。
        """
        env = self._envs.get(env_id)
        if not env:
            raise ValueError(f"环境 {env_id} 不存在")

        episode = Episode(
            episode_id = str(uuid.uuid4()),
            env_id     = env_id,
            algorithm  = algorithm,
        )

        # 从随机初始状态出发
        state = random.choice(env.state_space)

        # SARSA 需要预选第一个动作
        if algorithm == RLAlgorithm.SARSA:
            sarsa = self._sarsa.get(agent_id)
            cur_action = sarsa.choose_action(state, env.action_space) if sarsa else random.choice(env.action_space)
        else:
            cur_action = None

        for _ in range(env.max_steps):
            # ── 选择动作 ──
            if algorithm == RLAlgorithm.Q_LEARNING:
                qt     = self._q_tabs.get(agent_id)
                action = qt.choose_action(state, env.action_space) if qt else random.choice(env.action_space)

            elif algorithm == RLAlgorithm.SARSA:
                action = cur_action  # 使用之前选好的动作

            elif algorithm == RLAlgorithm.DQN:
                dqn    = self._dqn.get(agent_id)
                action = dqn.choose_action(state, env.action_space) if dqn else random.choice(env.action_space)

            elif algorithm == RLAlgorithm.REINFORCE:
                pg     = self._pg_ags.get(agent_id)
                action, _ = pg.choose_action(state, env.action_space) if pg else (random.choice(env.action_space), 0.5)

            elif algorithm == RLAlgorithm.UCB_BANDIT:
                bandit = self._bandits.get(agent_id)
                action = bandit.choose_action(state, env.action_space) if bandit else random.choice(env.action_space)

            else:
                action = random.choice(env.action_space)

            # ── 与环境交互 ──
            next_state, reward, done = reward_func(state, action)

            exp = Experience(state=state, action=action, reward=reward,
                             next_state=next_state, done=done)
            episode.add(exp)

            # ── 在线更新 ──
            if algorithm == RLAlgorithm.Q_LEARNING:
                qt = self._q_tabs.get(agent_id)
                if qt:
                    qt.update(exp, env.action_space)

            elif algorithm == RLAlgorithm.SARSA:
                sarsa = self._sarsa.get(agent_id)
                if sarsa:
                    # 预选下一步动作（on-policy）
                    next_action = sarsa.choose_action(next_state, env.action_space) if not done else ""
                    sarsa.update(state, action, reward, next_state, next_action, done)
                    cur_action = next_action

            elif algorithm == RLAlgorithm.DQN:
                dqn = self._dqn.get(agent_id)
                if dqn:
                    dqn.store(exp)
                    dqn.update(env.action_space)

            elif algorithm == RLAlgorithm.UCB_BANDIT:
                bandit = self._bandits.get(agent_id)
                if bandit:
                    bandit.update(action, reward)

            state = next_state
            if done:
                break

        episode.finish()

        # REINFORCE：回合结束后批量更新
        if algorithm == RLAlgorithm.REINFORCE:
            pg = self._pg_ags.get(agent_id)
            if pg:
                pg.update_episode(episode.experiences, env.action_space)

        # 衰减探索率（适用的算法）
        if algorithm == RLAlgorithm.Q_LEARNING:
            qt = self._q_tabs.get(agent_id)
            if qt:
                qt.decay_epsilon()
        elif algorithm == RLAlgorithm.SARSA:
            sarsa = self._sarsa.get(agent_id)
            if sarsa:
                sarsa.decay_epsilon()
        elif algorithm == RLAlgorithm.DQN:
            dqn = self._dqn.get(agent_id)
            if dqn:
                dqn.decay_epsilon()

        # 持久化
        self._save_episode(agent_id, episode)
        self._update_agent_stats(agent_id, episode.total_reward, algorithm)

        return {
            "episode_id"  : episode.episode_id,
            "total_reward": episode.total_reward,
            "steps"       : episode.steps,
            "status"      : episode.status,
        }

    def run_batch_episodes(
        self,
        agent_id    : str,
        env_id      : str,
        reward_func : Any,
        algorithm   : str,
        n_episodes  : int = 10,
    ) -> List[dict]:
        """连续训练 n 个 Episode，返回结果列表"""
        results = []
        for _ in range(n_episodes):
            r = self.run_episode(agent_id, env_id, reward_func, algorithm)
            results.append(r)
        return results

    # ─── 查询接口 ───────────────────────────────────────────────────────────────

    def get_episodes(self, agent_id: str, limit: int = 50) -> List[dict]:
        with _get_conn() as conn:
            rows = conn.execute(
                """SELECT * FROM rl_episodes
                   WHERE agent_id=? ORDER BY start_time DESC LIMIT ?""",
                (agent_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_episode_detail(self, episode_id: str) -> Optional[dict]:
        with _get_conn() as conn:
            ep_row = conn.execute(
                "SELECT * FROM rl_episodes WHERE episode_id=?", (episode_id,)
            ).fetchone()
            if not ep_row:
                return None
            exp_rows = conn.execute(
                "SELECT * FROM rl_experiences WHERE episode_id=? ORDER BY step",
                (episode_id,),
            ).fetchall()
        return {
            "episode"    : dict(ep_row),
            "experiences": [dict(r) for r in exp_rows],
        }

    def get_training_curve(self, agent_id: str) -> dict:
        """返回训练曲线数据（episode 序号 vs 累计奖励）"""
        with _get_conn() as conn:
            rows = conn.execute(
                """SELECT rowid, total_reward, steps
                   FROM rl_episodes WHERE agent_id=?
                   ORDER BY start_time ASC""",
                (agent_id,),
            ).fetchall()

        rewards = [r["total_reward"] for r in rows]
        steps   = [r["steps"]        for r in rows]

        # 移动平均（窗口=5）
        def moving_avg(data, w=5):
            out = []
            for i in range(len(data)):
                window = data[max(0, i - w + 1): i + 1]
                out.append(sum(window) / len(window))
            return out

        return {
            "episodes"   : list(range(1, len(rewards) + 1)),
            "rewards"    : rewards,
            "avg_rewards": moving_avg(rewards),
            "steps"      : steps,
        }

    def get_agent_info(self, agent_id: str) -> Optional[dict]:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM rl_agents WHERE agent_id=?", (agent_id,)
            ).fetchone()
        return dict(row) if row else None

    def get_q_table(self, agent_id: str) -> Optional[dict]:
        """获取 Q 表内容（用于可视化，支持 Q-Learning / SARSA / DQN）"""
        qt = self._q_tabs.get(agent_id)
        if qt:
            return qt.to_dict()
        sarsa = self._sarsa.get(agent_id)
        if sarsa:
            return sarsa.to_dict()
        dqn = self._dqn.get(agent_id)
        if dqn:
            # 把 DQN 权重转为 Q 表格式供可视化
            table = {}
            for key, val in dqn._weights.items():
                parts = key.split("||", 1)
                if len(parts) == 2:
                    s, a = parts
                    table.setdefault(s, {})[a] = val
            return {"alpha": dqn.alpha, "gamma": dqn.gamma,
                    "epsilon": dqn.epsilon, "table": table}
        bandit = self._bandits.get(agent_id)
        if bandit:
            return {
                "c": bandit.c,
                "counts": bandit._counts,
                "values": bandit._values,
                "table": {"bandit": bandit._values},
            }
        return None

    def delete_agent(self, agent_id: str) -> bool:
        """删除一个 Agent 及其所有训练历史"""
        # 从内存中移除
        self._q_tabs.pop(agent_id, None)
        self._pg_ags.pop(agent_id, None)
        self._sarsa.pop(agent_id, None)
        self._dqn.pop(agent_id, None)
        self._bandits.pop(agent_id, None)

        with _get_conn() as conn:
            # 删除相关经验
            conn.execute(
                """DELETE FROM rl_experiences WHERE episode_id IN
                   (SELECT episode_id FROM rl_episodes WHERE agent_id=?)""",
                (agent_id,))
            conn.execute("DELETE FROM rl_episodes WHERE agent_id=?", (agent_id,))
            conn.execute("DELETE FROM rl_agents WHERE agent_id=?", (agent_id,))
        return True

    def reset_agent(self, agent_id: str) -> bool:
        """重置 Agent 参数（保留 Agent 记录，清除训练数据）"""
        info = self.get_agent_info(agent_id)
        if not info:
            return False
        algorithm = info["algorithm"]

        # 重建新实例
        if algorithm == RLAlgorithm.Q_LEARNING:
            old = self._q_tabs.get(agent_id)
            if old:
                self._q_tabs[agent_id] = QTable(old.alpha, old.gamma, 0.3)
        elif algorithm == RLAlgorithm.SARSA:
            old = self._sarsa.get(agent_id)
            if old:
                self._sarsa[agent_id] = SARSATable(old.alpha, old.gamma, 0.3)
        elif algorithm == RLAlgorithm.DQN:
            old = self._dqn.get(agent_id)
            if old:
                self._dqn[agent_id] = SimpleDQN(old.alpha, old.gamma, 0.5, old.tau)
        elif algorithm == RLAlgorithm.REINFORCE:
            old = self._pg_ags.get(agent_id)
            if old:
                self._pg_ags[agent_id] = PolicyGradientAgent(old.gamma, old.lr)
        elif algorithm == RLAlgorithm.UCB_BANDIT:
            old = self._bandits.get(agent_id)
            if old:
                self._bandits[agent_id] = UCBBandit(old.c)

        # 清数据库训练记录
        with _get_conn() as conn:
            conn.execute(
                """DELETE FROM rl_experiences WHERE episode_id IN
                   (SELECT episode_id FROM rl_episodes WHERE agent_id=?)""",
                (agent_id,))
            conn.execute("DELETE FROM rl_episodes WHERE agent_id=?", (agent_id,))
            conn.execute(
                "UPDATE rl_agents SET episodes_done=0, best_reward=0.0, updated_at=? WHERE agent_id=?",
                (time.time(), agent_id))
        return True

    def delete_environment(self, env_id: str) -> bool:
        """删除环境及关联的所有 Agent"""
        if env_id not in self._envs:
            return False
        # 删除关联 Agent
        agents = self.list_agents(env_id)
        for ag in agents:
            self.delete_agent(ag["agent_id"])
        # 删除环境
        del self._envs[env_id]
        with _get_conn() as conn:
            conn.execute("DELETE FROM rl_environments WHERE env_id=?", (env_id,))
        return True

    def compare_agents(self, agent_ids: List[str]) -> dict:
        """比较多个 Agent 的训练表现"""
        results = {}
        for aid in agent_ids:
            info  = self.get_agent_info(aid)
            curve = self.get_training_curve(aid)
            if info and curve:
                rewards = curve.get("rewards", [])
                results[aid] = {
                    "algorithm"    : info.get("algorithm"),
                    "episodes_done": info.get("episodes_done", 0),
                    "best_reward"  : info.get("best_reward", 0),
                    "avg_reward"   : sum(rewards) / len(rewards) if rewards else 0,
                    "last_10_avg"  : sum(rewards[-10:]) / len(rewards[-10:]) if rewards else 0,
                    "curve"        : curve,
                }
        return results

    def cleanup_legacy_demo_environments(self) -> int:
        """移除早期偏游戏化/金融化的演示环境，保留面向 LLM/Agent 的场景。"""
        legacy_names = {
            "网格迷宫",
            "提示词优化",
            "悬崖行走",
            "多臂老虎机",
            "股票交易",
        }
        legacy_env_ids = [
            env.env_id
            for env in self._envs.values()
            if env.name in legacy_names
        ]
        for env_id in legacy_env_ids:
            self.delete_environment(env_id)
        return len(legacy_env_ids)

    # ─── 内置演示环境 ──────────────────────────────────────────────────────────

    def create_demo_environments(self):
        """创建贴近 LLM / Agent 工作流的默认场景环境。"""
        # 场景1：指令遵循与回复策略
        if not any(e.name == "指令遵循与回复策略" for e in self._envs.values()):
            self.create_environment(
                name        = "指令遵循与回复策略",
                description = "面向大模型回复生成：在普通问答、结构化输出、信息缺失和高风险请求之间选择合适的响应策略。",
                state_space = ["普通问答", "结构化输出", "信息缺失", "高风险请求", "最终回复"],
                action_space= ["直接回答", "结构化回答", "先澄清", "拒答并解释", "调用工具后回答"],
                max_steps   = 20,
            )

        # 场景2：RAG 检索决策
        if not any(e.name == "RAG检索决策" for e in self._envs.values()):
            self.create_environment(
                name        = "RAG检索决策",
                description = "面向检索增强问答：根据证据充分度、冲突度和引用需求选择继续检索、直接回答或请求补充上下文。",
                state_space = ["证据充分", "证据冲突", "证据不足", "需要引用", "完成"],
                action_space= ["直接作答", "引用证据作答", "继续检索", "请求补充上下文", "保守拒答"],
                max_steps   = 18,
            )

        # 场景3：工具调用代理
        if not any(e.name == "工具调用代理" for e in self._envs.values()):
            self.create_environment(
                name        = "工具调用代理",
                description = "面向 Agent 工作流：在日志排查、知识库查询、执行验证和输出修复建议之间学习最优动作顺序。",
                state_space = ["接收任务", "查看日志", "核对知识库", "执行验证", "输出结论"],
                action_space= ["读日志", "查知识库", "执行检查项", "生成修复建议", "升级人工"],
                max_steps   = 24,
            )

        # 场景4：偏好数据采样
        if not any(e.name == "偏好数据采样" for e in self._envs.values()):
            self.create_environment(
                name        = "偏好数据采样",
                description = "面向 RLHF / DPO 数据生产：学习何时生成对比样本、请求人工偏好以及将高质量样本写回数据集。",
                state_space = ["生成候选", "对比构造", "等待偏好", "写回数据集", "批次完成"],
                action_space= ["采样多样回复", "生成安全基线", "请求人工标注", "导出DPO样本", "丢弃低质量样本"],
                max_steps   = 16,
            )

        # 场景5：运维工单诊断
        if not any(e.name == "运维工单诊断" for e in self._envs.values()):
            self.create_environment(
                name        = "运维工单诊断",
                description = "贴合平台主场景：围绕告警初判、SOP 检索、日志排查和结构化工单输出构建闭环反馈。",
                state_space = ["告警初判", "需要查手册", "需要查日志", "需要生成工单", "闭环完成"],
                action_space= ["直接给建议", "检索SOP", "调用日志工具", "生成结构化报告", "升级专家"],
                max_steps   = 18,
            )

    # ─── 私有方法 ──────────────────────────────────────────────────────────────

    def _save_environment(self, env: RLEnvironment):
        with _get_conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO rl_environments
                   (env_id, name, description, state_space, action_space, max_steps, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (env.env_id, env.name, env.description,
                 json.dumps(env.state_space, ensure_ascii=False),
                 json.dumps(env.action_space, ensure_ascii=False),
                 env.max_steps, env.created_at),
            )

    def _save_episode(self, agent_id: str, episode: Episode):
        with _get_conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO rl_episodes
                   (episode_id, agent_id, env_id, algorithm, total_reward,
                    steps, status, start_time, end_time)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (episode.episode_id, agent_id, episode.env_id, episode.algorithm,
                 episode.total_reward, episode.steps, episode.status,
                 episode.start_time, episode.end_time),
            )
            for i, exp in enumerate(episode.experiences):
                conn.execute(
                    """INSERT INTO rl_experiences
                       (episode_id, step, state, action, reward, next_state, done, timestamp, metadata)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (episode.episode_id, i, exp.state, exp.action, exp.reward,
                     exp.next_state, int(exp.done), exp.timestamp,
                     json.dumps(exp.metadata)),
                )

    def _update_agent_stats(self, agent_id: str, episode_reward: float, algorithm: str):
        """更新 Agent 的 episodes_done / best_reward / params"""
        if algorithm == RLAlgorithm.Q_LEARNING and agent_id in self._q_tabs:
            params = json.dumps(self._q_tabs[agent_id].to_dict())
        elif algorithm == RLAlgorithm.SARSA and agent_id in self._sarsa:
            params = json.dumps(self._sarsa[agent_id].to_dict())
        elif algorithm == RLAlgorithm.DQN and agent_id in self._dqn:
            params = json.dumps(self._dqn[agent_id].to_dict())
        elif algorithm == RLAlgorithm.REINFORCE and agent_id in self._pg_ags:
            params = json.dumps(self._pg_ags[agent_id].to_dict())
        elif algorithm == RLAlgorithm.UCB_BANDIT and agent_id in self._bandits:
            params = json.dumps(self._bandits[agent_id].to_dict())
        else:
            params = "{}"

        with _get_conn() as conn:
            conn.execute(
                """UPDATE rl_agents SET
                     episodes_done = episodes_done + 1,
                     best_reward   = MAX(best_reward, ?),
                     params        = ?,
                     updated_at    = ?
                   WHERE agent_id = ?""",
                (episode_reward, params, time.time(), agent_id),
            )

    def _load_all(self):
        """启动时从数据库恢复已有环境和 Agent"""
        with _get_conn() as conn:
            for row in conn.execute("SELECT * FROM rl_environments").fetchall():
                env = RLEnvironment(
                    env_id      = row["env_id"],
                    name        = row["name"],
                    description = row["description"],
                    state_space = json.loads(row["state_space"]),
                    action_space= json.loads(row["action_space"]),
                    max_steps   = row["max_steps"],
                    created_at  = row["created_at"],
                )
                self._envs[env.env_id] = env

            for row in conn.execute("SELECT * FROM rl_agents").fetchall():
                alg    = row["algorithm"]
                params = json.loads(row["params"])
                agent_id = row["agent_id"]
                if alg == RLAlgorithm.Q_LEARNING and "table" in params:
                    self._q_tabs[agent_id] = QTable.from_dict(params)
                elif alg == RLAlgorithm.SARSA and "table" in params:
                    self._sarsa[agent_id] = SARSATable.from_dict(params)
                elif alg == RLAlgorithm.DQN and "weights" in params:
                    self._dqn[agent_id] = SimpleDQN.from_dict(params)
                elif alg == RLAlgorithm.REINFORCE and "scores" in params:
                    self._pg_ags[agent_id] = PolicyGradientAgent.from_dict(params)
                elif alg == RLAlgorithm.UCB_BANDIT and "values" in params:
                    self._bandits[agent_id] = UCBBandit.from_dict(params)


# ─── 内置奖励函数库 ────────────────────────────────────────────────────────────

def _bounded_reward(base: float, noise: float = 0.04) -> float:
    return max(-1.0, min(1.0, base + random.gauss(0, noise)))


def _sample_next_state(state: str, transitions: Dict[str, Dict[str, float]], default_done: str) -> Tuple[str, bool]:
    probs = transitions.get(state)
    if not probs:
        return default_done, True
    states = list(probs.keys())
    weights = list(probs.values())
    next_state = random.choices(states, weights=weights)[0]
    return next_state, next_state == default_done


def instruction_policy_reward_func(state: str, action: str) -> Tuple[str, float, bool]:
    """面向回复策略选择的奖励函数。"""
    rewards = {
        ("普通问答", "直接回答"): 0.85,
        ("普通问答", "调用工具后回答"): 0.55,
        ("结构化输出", "结构化回答"): 0.95,
        ("结构化输出", "直接回答"): 0.35,
        ("信息缺失", "先澄清"): 0.95,
        ("信息缺失", "调用工具后回答"): 0.72,
        ("高风险请求", "拒答并解释"): 1.00,
        ("高风险请求", "先澄清"): 0.55,
    }
    transitions = {
        "普通问答": {"结构化输出": 0.35, "信息缺失": 0.30, "高风险请求": 0.10, "最终回复": 0.25},
        "结构化输出": {"普通问答": 0.35, "信息缺失": 0.15, "最终回复": 0.50},
        "信息缺失": {"普通问答": 0.40, "结构化输出": 0.25, "最终回复": 0.35},
        "高风险请求": {"最终回复": 0.60, "普通问答": 0.40},
        "最终回复": {"最终回复": 1.0},
    }
    next_state, done = _sample_next_state(state, transitions, "最终回复")
    return next_state, _bounded_reward(rewards.get((state, action), 0.18)), done


def rag_reward_func(state: str, action: str) -> Tuple[str, float, bool]:
    """面向 RAG / 证据使用策略的奖励函数。"""
    rewards = {
        ("证据充分", "引用证据作答"): 0.97,
        ("证据充分", "直接作答"): 0.76,
        ("证据冲突", "继续检索"): 0.95,
        ("证据冲突", "保守拒答"): 0.55,
        ("证据不足", "请求补充上下文"): 0.90,
        ("证据不足", "继续检索"): 0.82,
        ("需要引用", "引用证据作答"): 1.00,
        ("需要引用", "直接作答"): 0.25,
    }
    transitions = {
        "证据充分": {"需要引用": 0.30, "完成": 0.55, "证据冲突": 0.15},
        "证据冲突": {"证据充分": 0.45, "证据不足": 0.20, "完成": 0.35},
        "证据不足": {"证据充分": 0.35, "需要引用": 0.15, "完成": 0.20, "证据不足": 0.30},
        "需要引用": {"完成": 0.70, "证据充分": 0.30},
        "完成": {"完成": 1.0},
    }
    next_state, done = _sample_next_state(state, transitions, "完成")
    return next_state, _bounded_reward(rewards.get((state, action), 0.16)), done


def tool_agent_reward_func(state: str, action: str) -> Tuple[str, float, bool]:
    """面向工具调用代理的奖励函数。"""
    rewards = {
        ("接收任务", "读日志"): 0.78,
        ("接收任务", "查知识库"): 0.66,
        ("查看日志", "查知识库"): 0.86,
        ("查看日志", "执行检查项"): 0.80,
        ("核对知识库", "执行检查项"): 0.92,
        ("执行验证", "生成修复建议"): 0.97,
        ("执行验证", "升级人工"): 0.52,
        ("输出结论", "生成修复建议"): 1.00,
    }
    next_state = {
        ("接收任务", "读日志"): "查看日志",
        ("接收任务", "查知识库"): "核对知识库",
        ("查看日志", "查知识库"): "核对知识库",
        ("查看日志", "执行检查项"): "执行验证",
        ("核对知识库", "执行检查项"): "执行验证",
        ("执行验证", "生成修复建议"): "输出结论",
        ("执行验证", "升级人工"): "输出结论",
        ("输出结论", "生成修复建议"): "输出结论",
    }.get((state, action), random.choice(["查看日志", "核对知识库", "执行验证", "输出结论"]))
    done = next_state == "输出结论" and action in {"生成修复建议", "升级人工"}
    return next_state, _bounded_reward(rewards.get((state, action), 0.20)), done


def preference_data_reward_func(state: str, action: str) -> Tuple[str, float, bool]:
    """面向 RLHF / DPO 偏好数据生产的奖励函数。"""
    rewards = {
        ("生成候选", "采样多样回复"): 0.90,
        ("生成候选", "生成安全基线"): 0.75,
        ("对比构造", "生成安全基线"): 0.86,
        ("对比构造", "请求人工标注"): 0.66,
        ("等待偏好", "请求人工标注"): 0.96,
        ("等待偏好", "丢弃低质量样本"): 0.58,
        ("写回数据集", "导出DPO样本"): 1.00,
    }
    next_state = {
        ("生成候选", "采样多样回复"): "对比构造",
        ("生成候选", "生成安全基线"): "对比构造",
        ("对比构造", "生成安全基线"): "等待偏好",
        ("对比构造", "请求人工标注"): "等待偏好",
        ("等待偏好", "请求人工标注"): "写回数据集",
        ("等待偏好", "丢弃低质量样本"): "生成候选",
        ("写回数据集", "导出DPO样本"): "批次完成",
    }.get((state, action), random.choice(["生成候选", "对比构造", "等待偏好", "写回数据集"]))
    done = next_state == "批次完成"
    return next_state, _bounded_reward(rewards.get((state, action), 0.14)), done


def maintenance_ticket_reward_func(state: str, action: str) -> Tuple[str, float, bool]:
    """贴合运维场景的诊断闭环奖励函数。"""
    rewards = {
        ("告警初判", "检索SOP"): 0.82,
        ("告警初判", "调用日志工具"): 0.86,
        ("需要查手册", "检索SOP"): 0.98,
        ("需要查日志", "调用日志工具"): 1.00,
        ("需要生成工单", "生成结构化报告"): 1.00,
        ("需要查日志", "升级专家"): 0.46,
        ("告警初判", "升级专家"): 0.35,
    }
    next_state = {
        ("告警初判", "检索SOP"): "需要查手册",
        ("告警初判", "调用日志工具"): "需要查日志",
        ("告警初判", "直接给建议"): "需要生成工单",
        ("需要查手册", "检索SOP"): "需要生成工单",
        ("需要查日志", "调用日志工具"): "需要生成工单",
        ("需要查日志", "升级专家"): "闭环完成",
        ("需要生成工单", "生成结构化报告"): "闭环完成",
    }.get((state, action), random.choice(["需要查手册", "需要查日志", "需要生成工单"]))
    done = next_state == "闭环完成"
    return next_state, _bounded_reward(rewards.get((state, action), 0.18)), done


# 奖励函数注册表
REWARD_FUNCTIONS = {
    "指令遵循与回复策略": instruction_policy_reward_func,
    "RAG检索决策": rag_reward_func,
    "工具调用代理": tool_agent_reward_func,
    "偏好数据采样": preference_data_reward_func,
    "运维工单诊断": maintenance_ticket_reward_func,
}


# ─── 全局单例 ─────────────────────────────────────────────────────────────────

_rl_manager: Optional[RLManager] = None

def get_rl_manager() -> RLManager:
    global _rl_manager
    if _rl_manager is None:
        _rl_manager = RLManager()
        _rl_manager.cleanup_legacy_demo_environments()
        _rl_manager.create_demo_environments()
    return _rl_manager
